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
from dataclasses import dataclass, field
from typing import AsyncIterator

from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from loguru import logger

from app.retrieval.llm import get_llm
from app.retrieval.prompts import CONDENSE_PROMPT, QA_PROMPT, format_retrieved_docs
from app.retrieval.retriever import get_retriever

# ---------------------------------------------------------------------------
# In-process session store with LRU cache + TTL (replace with Redis for multi-pod)
# ---------------------------------------------------------------------------

# LRU session store with automatic eviction when max_size exceeded
# TTL_SECONDS: sessions older than this are automatically evicted
_SESSION_STORE: dict[str, tuple[ChatMessageHistory, float]] = {}
_MAX_SESSIONS = 1000  # LRU limit: max concurrent sessions in memory
_SESSION_TTL_SECONDS = 86400  # 24h TTL: sessions auto-evict after 24h of last access


def _evict_expired_sessions() -> None:
    """Remove sessions older than TTL_SECONDS. Called before each access."""
    current_time = time.time()
    expired = [
        sid for sid, (_, timestamp) in _SESSION_STORE.items()
        if current_time - timestamp > _SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _SESSION_STORE.pop(sid)
        logger.debug("Auto-evicted expired session: {}", sid)


def _evict_lru_session() -> None:
    """Remove least-recently-used session when max_size exceeded."""
    if len(_SESSION_STORE) >= _MAX_SESSIONS:
        # Find LRU (oldest timestamp)
        lru_sid = min(_SESSION_STORE.keys(), key=lambda s: _SESSION_STORE[s][1])
        _SESSION_STORE.pop(lru_sid)
        logger.debug("LRU evicted session: {}", lru_sid)


def _get_session_history(session_id: str) -> BaseChatMessageHistory:
    _evict_expired_sessions()
    _evict_lru_session()
    
    if session_id not in _SESSION_STORE:
        _SESSION_STORE[session_id] = (ChatMessageHistory(), time.time())
        logger.debug("New chat session: {}", session_id)
    else:
        # Update access timestamp for LRU tracking
        history, _ = _SESSION_STORE[session_id]
        _SESSION_STORE[session_id] = (history, time.time())
    
    return _SESSION_STORE[session_id][0]


def clear_session(session_id: str) -> None:
    """Delete the message history for *session_id*."""
    _SESSION_STORE.pop(session_id, None)
    logger.info("Cleared session: {}", session_id)


def list_sessions() -> list[str]:
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


def _get_rag_chain() -> RunnableWithMessageHistory:
    global _rag_chain
    if _rag_chain is None:
        logger.info("Building RAG chain (first call)…")
        _rag_chain = _build_rag_chain()
        logger.info("RAG chain ready")
    return _rag_chain


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
    if not question.strip():
        return RAGResponse(answer="Please provide a non-empty question.", session_id=session_id)

    chain = _get_rag_chain()
    t0 = time.perf_counter()

    logger.info("RAG query | session={} | question='{}'", session_id, question[:120])

    try:
        result: dict = chain.invoke(
            {"input": question},
            config={"configurable": {"session_id": session_id}},
        )
    except Exception as exc:
        logger.exception("RAG chain error for session {}: {}", session_id, exc)
        raise

    latency_ms = (time.perf_counter() - t0) * 1000
    answer: str = result.get("answer", "")
    context_docs: list = result.get("context", [])

    sources = _extract_sources(context_docs)

    logger.info(
        "RAG answer | session={} | chunks={} | latency={:.0f}ms | answer_len={}",
        session_id,
        len(context_docs),
        latency_ms,
        len(answer),
    )

    return RAGResponse(
        answer=answer,
        sources=sources,
        session_id=session_id,
        latency_ms=round(latency_ms, 1),
        retrieved_chunks=len(context_docs),
    )


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
