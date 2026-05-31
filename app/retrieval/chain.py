"""
LangChain RAG QA chain — the core of the system.

Architecture (LCEL):

  User question + chat history
        │
        ▼
  ┌─────────────────────────────────┐
  │  history_aware_retriever        │  ← CONDENSE_PROMPT + LLM reformulates
  │  (create_history_aware_retriever)│    follow-up questions into standalone
  └──────────────┬──────────────────┘    queries before hitting ChromaDB
                 │ retrieved Documents
                 ▼
  ┌─────────────────────────────────┐
  │  stuff_documents_chain          │  ← QA_PROMPT (anti-hallucination)
  │  (create_stuff_documents_chain) │    Context is formatted with source
  └──────────────┬──────────────────┘    citations before LLM sees it
                 │
                 ▼
              answer + source documents

Chat history is managed per session_id using LangChain's ChatMessageHistory.
Sessions are stored in-process (a dict); swap for Redis / DB in production.

The public interface:
    ask(question, session_id) → RAGResponse
    stream_ask(question, session_id) → AsyncIterator[str]
"""

from __future__ import annotations

import time
import threading
import sys
from dataclasses import dataclass, field
from typing import AsyncIterator

from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from loguru import logger
import numpy as np

from app.retrieval.llm import get_llm
from app.retrieval.prompts import CONDENSE_PROMPT, QA_PROMPT, format_retrieved_docs
from app.retrieval.retriever import get_retriever
from app.ingestion.embedder import get_embedding_model

# ---------------------------------------------------------------------------
# Thread-safe session store with LRU cache + TTL + memory monitoring
# ---------------------------------------------------------------------------

# LRU session store with automatic eviction when max_size exceeded
# TTL_SECONDS: sessions older than this are automatically evicted
_SESSION_STORE: dict[str, tuple[ChatMessageHistory, float]] = {}
_MAX_SESSIONS = 1000  # LRU limit: max concurrent sessions in memory
_SESSION_TTL_SECONDS = 86400  # 24h TTL: sessions auto-evict after 24h of last access
_SESSION_LOCK = threading.RLock()  # Thread-safe access to session store
_MEMORY_CHECK_INTERVAL = 100  # Check memory stats every N operations
_OPERATION_COUNT = 0


def _get_session_memory_usage() -> float:
    """Estimate memory usage of session store in MB."""
    size_bytes = sys.getsizeof(_SESSION_STORE)
    for session_id, (history, _) in _SESSION_STORE.items():
        size_bytes += sys.getsizeof(session_id)
        size_bytes += sys.getsizeof(history)
        for msg in history.messages:
            size_bytes += sys.getsizeof(msg)
    return size_bytes / (1024 * 1024)


def _evict_expired_sessions() -> None:
    """Remove sessions older than TTL_SECONDS. Called before each access."""
    current_time = time.time()
    expired = [
        sid for sid, (_, timestamp) in _SESSION_STORE.items()
        if current_time - timestamp > _SESSION_TTL_SECONDS
    ]
    if expired:
        memory_before = _get_session_memory_usage()
        for sid in expired:
            _SESSION_STORE.pop(sid)
        memory_after = _get_session_memory_usage()
        logger.debug(f"Auto-evicted {len(expired)} expired sessions. Memory freed: {memory_before - memory_after:.2f}MB")


def _evict_lru_session() -> None:
    """Remove least-recently-used session when max_size exceeded."""
    if len(_SESSION_STORE) >= _MAX_SESSIONS:
        # Find LRU (oldest timestamp)
        lru_sid = min(_SESSION_STORE.keys(), key=lambda s: _SESSION_STORE[s][1])
        _SESSION_STORE.pop(lru_sid)
        logger.debug(f"LRU evicted session: {lru_sid}")


def _get_session_history(session_id: str) -> BaseChatMessageHistory:
    global _OPERATION_COUNT
    
    with _SESSION_LOCK:
        _OPERATION_COUNT += 1
        
        # Periodic memory check and logging
        if _OPERATION_COUNT % _MEMORY_CHECK_INTERVAL == 0:
            mem_usage = _get_session_memory_usage()
            logger.debug(f"Session store: {len(_SESSION_STORE)} sessions, {mem_usage:.2f}MB memory")
        
        _evict_expired_sessions()
        _evict_lru_session()
        
        if session_id not in _SESSION_STORE:
            _SESSION_STORE[session_id] = (ChatMessageHistory(), time.time())
            logger.debug(f"New chat session: {session_id}")
        else:
            # Update access timestamp for LRU tracking
            history, _ = _SESSION_STORE[session_id]
            _SESSION_STORE[session_id] = (history, time.time())
        
        return _SESSION_STORE[session_id][0]


def clear_session(session_id: str) -> None:
    """Delete the message history for *session_id*."""
    with _SESSION_LOCK:
        _SESSION_STORE.pop(session_id, None)
        logger.info(f"Cleared session: {session_id}")


def list_sessions() -> list[str]:
    with _SESSION_LOCK:
        _evict_expired_sessions()
        return list(_SESSION_STORE.keys())


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SourceDocument:
    file_name: str
    source: str
    chunk_id: str
    page: str | int
    snippet: str          # first 200 chars of the chunk for UI preview


@dataclass
class RAGResponse:
    answer: str
    sources: list[SourceDocument] = field(default_factory=list)
    session_id: str = ""
    latency_ms: float = 0.0
    retrieved_chunks: int = 0
    cache_hit: bool = False  # True if answer came from query cache


# ---------------------------------------------------------------------------
# Chain factory (built once, reused across requests)
# ---------------------------------------------------------------------------

def _build_rag_chain() -> RunnableWithMessageHistory:
    llm = get_llm()
    retriever = get_retriever()

    # Stage 1 — rewrite the user question as a standalone query when there
    # is chat history (no-op when history is empty)
    history_aware_retriever = create_history_aware_retriever(
        llm=llm,
        retriever=retriever,
        prompt=CONDENSE_PROMPT,
    )

    # Stage 2 — stuff retrieved docs into the anti-hallucination QA prompt
    # and generate the answer
    qa_chain = create_stuff_documents_chain(
        llm=llm,
        prompt=QA_PROMPT,
        document_prompt=None,      # use default passthrough
        document_separator="\n\n---\n\n",
    )

    # Stage 3 — wire retriever + QA chain together
    retrieval_chain = create_retrieval_chain(
        retriever=history_aware_retriever,
        combine_docs_chain=qa_chain,
    )

    # Stage 4 — wrap with automatic session history management
    return RunnableWithMessageHistory(
        retrieval_chain,
        get_session_history=_get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )


# Lazy singleton — built on first call
_rag_chain: RunnableWithMessageHistory | None = None

# Query result cache: (session_id, question_hash) → (RAGResponse, timestamp, embedding)
# Prevents redundant LLM pipeline execution for identical AND semantically similar questions
_QUERY_CACHE: dict[tuple[str, int], tuple[RAGResponse, float, list]] = {}
_QUERY_CACHE_MAX_SIZE = 500  # LRU limit for cached queries
_QUERY_CACHE_TTL_SECONDS = 3600  # 1h TTL: cached results expire after 1h
_SEMANTIC_SIMILARITY_THRESHOLD = 0.85  # Min cosine similarity (0.0-1.0) to reuse cached answer

# Cache statistics tracking
_CACHE_STATS = {
    "total_queries": 0,
    "exact_hits": 0,
    "semantic_hits": 0,
    "misses": 0,
}


def _get_rag_chain() -> RunnableWithMessageHistory:
    global _rag_chain
    if _rag_chain is None:
        logger.info("Building RAG chain (first call)…")
        _rag_chain = _build_rag_chain()
        logger.info("RAG chain ready")
    return _rag_chain


def _query_cache_key(question: str, session_id: str) -> tuple[str, int]:
    """Generate cache key from question + session_id."""
    return (session_id, hash(question.strip().lower()))


def _evict_expired_queries() -> None:
    """Remove cached queries older than TTL."""
    current_time = time.time()
    expired = [
        key for key, (_, timestamp, _) in _QUERY_CACHE.items()
        if current_time - timestamp > _QUERY_CACHE_TTL_SECONDS
    ]
    for key in expired:
        _QUERY_CACHE.pop(key)
        logger.debug("Query cache: evicted expired entry")


def _evict_lru_query() -> None:
    """Remove least-recently-used cached query when max_size exceeded."""
    if len(_QUERY_CACHE) >= _QUERY_CACHE_MAX_SIZE:
        # Find LRU (oldest timestamp)
        lru_key = min(_QUERY_CACHE.keys(), key=lambda k: _QUERY_CACHE[k][1])
        _QUERY_CACHE.pop(lru_key)
        logger.debug("Query cache: LRU evicted entry")


def _find_semantically_similar_cached_answer(
    question: str,
    session_id: str,
) -> RAGResponse | None:
    """
    Search cache for semantically similar questions (cosine similarity > threshold).
    
    Uses dot product for cosine similarity since embeddings are already normalized
    (set via normalize_embeddings=True in embedder config).
    
    Returns cached RAGResponse if found, else None.
    """
    try:
        # Get embedding for incoming question
        embedder = get_embedding_model()
        question_embedding = np.array(embedder.embed_query(question.strip().lower()))
        
        # Search for similar cached entries in same session
        for (cache_session, _), (response, _, cached_embedding) in _QUERY_CACHE.items():
            if cache_session != session_id or not cached_embedding:
                continue
            
            # Compute cosine similarity via dot product (embeddings are normalized)
            cached_vec = np.array(cached_embedding)
            similarity = float(np.dot(question_embedding, cached_vec))
            
            if similarity >= _SEMANTIC_SIMILARITY_THRESHOLD:
                logger.debug(
                    f"Query cache SEMANTIC HIT | session={session_id} | similarity={similarity:.3f}"
                )
                _CACHE_STATS["semantic_hits"] += 1
                return response
    except Exception as e:
        logger.warning(f"Semantic similarity lookup failed (falling through): {e}")
        # Fall through to full pipeline on error
    
    return None


def get_query_cache_stats() -> dict:
    """Return query cache statistics for monitoring."""
    total = _CACHE_STATS["total_queries"]
    exact = _CACHE_STATS["exact_hits"]
    semantic = _CACHE_STATS["semantic_hits"]
    hits = exact + semantic
    hit_rate = (hits / total * 100) if total > 0 else 0
    
    return {
        "total_queries": total,
        "exact_hits": exact,
        "semantic_hits": semantic,
        "total_hits": hits,
        "misses": _CACHE_STATS["misses"],
        "hit_rate_percent": round(hit_rate, 2),
        "cache_size": len(_QUERY_CACHE),
        "max_size": _QUERY_CACHE_MAX_SIZE,
    }


def clear_query_cache() -> int:
    """Clear all cached queries. Returns count of cleared entries."""
    global _QUERY_CACHE, _CACHE_STATS
    cleared = len(_QUERY_CACHE)
    _QUERY_CACHE.clear()
    _CACHE_STATS = {"total_queries": 0, "exact_hits": 0, "semantic_hits": 0, "misses": 0}
    logger.info(f"Query cache cleared ({cleared} entries)")
    return cleared


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(question: str, session_id: str = "default") -> RAGResponse:
    """
    Run the full RAG pipeline synchronously.

    Args:
        question:   The user's natural-language question.
        session_id: Identifies the conversation thread.
                    Different session_ids maintain independent histories.

    Returns:
        RAGResponse with answer, sources, and latency.
    """
    _CACHE_STATS["total_queries"] += 1
    
    if not question.strip():
        return RAGResponse(answer="Please provide a non-empty question.", session_id=session_id)

    # Check query result cache (exact match first, then semantic)
    cache_key = _query_cache_key(question, session_id)
    _evict_expired_queries()
    
    if cache_key in _QUERY_CACHE:
        cached_response, _, _ = _QUERY_CACHE[cache_key]
        cached_response.cache_hit = True
        _CACHE_STATS["exact_hits"] += 1
        logger.debug(f"Query cache EXACT HIT | session={session_id} | question='{question[:120]}'")
        return cached_response
    
    # Try semantic similarity lookup
    semantic_match = _find_semantically_similar_cached_answer(question, session_id)
    if semantic_match is not None:
        semantic_match.cache_hit = True
        return semantic_match

    _CACHE_STATS["misses"] += 1
    chain = _get_rag_chain()
    t0 = time.perf_counter()

    logger.info(f"RAG query | session={session_id} | question='{question[:120]}'")

    try:
        result: dict = chain.invoke(
            {"input": question},
            config={"configurable": {"session_id": session_id}},
        )
    except Exception as exc:
        logger.exception(f"RAG chain error for session {session_id}: {exc}")
        raise

    latency_ms = (time.perf_counter() - t0) * 1000
    answer: str = result.get("answer", "")
    context_docs: list = result.get("context", [])

    sources = _extract_sources(context_docs)

    logger.info(
        f"RAG answer | session={session_id} | chunks={len(context_docs)} | latency={latency_ms:.0f}ms | answer_len={len(answer)}"
    )

    response = RAGResponse(
        answer=answer,
        sources=sources,
        session_id=session_id,
        latency_ms=round(latency_ms, 1),
        retrieved_chunks=len(context_docs),
    )

    # Cache the result with embedding for semantic similarity
    _evict_lru_query()
    try:
        embedder = get_embedding_model()
        question_embedding = embedder.embed_query(question.strip().lower())
        _QUERY_CACHE[cache_key] = (response, time.time(), question_embedding)
        logger.debug(f"Query cache MISS→STORE | session={session_id} | embedding cached")
    except Exception as e:
        logger.warning(f"Failed to cache embedding for query: {e}")
        # Still cache response even if embedding failed
        _QUERY_CACHE[cache_key] = (response, time.time(), [])

    return response


async def stream_ask(
    question: str,
    session_id: str = "default",
) -> AsyncIterator[str]:
    """
    Stream the answer token-by-token.

    Yields raw string tokens; the caller (FastAPI endpoint) wraps them in
    Server-Sent Events or WebSocket messages.
    """
    if not question.strip():
        yield "Please provide a non-empty question."
        return

    chain = _get_rag_chain()
    logger.info("RAG stream | session={} | question='{}'", session_id, question[:120])

    try:
        async for chunk in chain.astream(
            {"input": question},
            config={"configurable": {"session_id": session_id}},
        ):
            # astream yields dicts; the answer token lives under "answer"
            token = chunk.get("answer", "")
            if token:
                yield token
    except Exception as exc:
        logger.exception("RAG stream error for session {}: {}", session_id, exc)
        yield f"\n\n[Error: {exc}]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_sources(docs: list) -> list[SourceDocument]:
    seen: set[str] = set()
    sources: list[SourceDocument] = []

    for doc in docs:
        meta = doc.metadata
        chunk_id = meta.get("chunk_id", "")
        if chunk_id in seen:
            continue
        seen.add(chunk_id)

        sources.append(
            SourceDocument(
                file_name=meta.get("file_name", "unknown"),
                source=meta.get("source", ""),
                chunk_id=chunk_id,
                page=meta.get("page", meta.get("chunk_index", "")),
                snippet=doc.page_content[:200].replace("\n", " "),
            )
        )

    return sources
