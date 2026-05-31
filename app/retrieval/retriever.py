"""
Retriever layer.

Two retrieval modes, selectable at runtime:

  STANDARD  — vanilla similarity search against child chunks.
              Fast, good for most use-cases.

  PARENT    — retrieves small child chunks (high recall) then swaps in their
              larger parent chunks (rich context) before passing to the LLM.
              Reduces the "lost in the middle" problem on long documents.

The public interface is a single function:
    get_retriever() → BaseRetriever

Both modes return a LangChain-compatible BaseRetriever so the chain code
never needs to know which mode is active.
"""

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from loguru import logger
from pydantic import Field

from app.core.config import settings
from app.retrieval.vector_store import get_langchain_vector_store

_PARENT_STORE_PATH = Path("data/processed/parent_store.json")

# Cached parent store (loaded once, reused across requests)
_PARENT_STORE_CACHE: dict[str, Document] | None = None
_PARENT_STORE_BUILD_TIME: float = 0.0

# Cached retriever singleton (built once, reused across requests)
_RETRIEVER_CACHE: BaseRetriever | None = None
_RETRIEVER_BUILD_TIME: float = 0.0
_RETRIEVER_CONFIG: dict[str, Any] | None = None  # Track which config was used


# ---------------------------------------------------------------------------
# Parent-chunk docstore (loaded once, cached across requests)
# ---------------------------------------------------------------------------

def _load_parent_store() -> dict[str, Document]:
    """
    Load the JSON parent store written by IngestionPipeline into a dict.
    
    Cached singleton — loaded once from disk and reused. If the file is
    modified after first load, restart the app to reload.

    Returns an empty dict (gracefully) if the store does not exist yet —
    the retriever will then fall back to child chunks.
    """
    global _PARENT_STORE_CACHE, _PARENT_STORE_BUILD_TIME
    
    # Return cached store if already loaded
    if _PARENT_STORE_CACHE is not None:
        return _PARENT_STORE_CACHE
    
    load_start = time.perf_counter()
    
    if not _PARENT_STORE_PATH.exists():
        logger.warning(
            f"Parent store not found at '{_PARENT_STORE_PATH}' — falling back to child chunks"
        )
        _PARENT_STORE_CACHE = {}
        return _PARENT_STORE_CACHE

    with _PARENT_STORE_PATH.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    store = {
        pid: Document(
            page_content=entry["page_content"],
            metadata=entry["metadata"],
        )
        for pid, entry in raw.items()
    }
    
    load_time_ms = (time.perf_counter() - load_start) * 1000
    _PARENT_STORE_BUILD_TIME = load_time_ms
    logger.info(f"Loaded {len(store)} parent chunks from docstore in {load_time_ms:.2f}ms (cached)")
    _PARENT_STORE_CACHE = store
    return store


# ---------------------------------------------------------------------------
# Standard retriever (thin wrapper, adds logging)
# ---------------------------------------------------------------------------

class StandardRetriever(BaseRetriever):
    """Wraps a LangChain VectorStore retriever with structured logging and optional metadata filtering."""

    vector_store: VectorStore
    top_k: int = Field(default=6)
    filter_metadata: dict | None = Field(default=None)  # Optional metadata filters

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        # Apply metadata filter if provided
        if self.filter_metadata:
            docs = self.vector_store.similarity_search(
                query, 
                k=self.top_k,
                filter=self.filter_metadata
            )
            logger.debug(f"Standard retriever: {len(docs)} doc(s) for query '{query[:80]}' (filtered: {self.filter_metadata})")
        else:
            docs = self.vector_store.similarity_search(query, k=self.top_k)
            logger.debug(f"Standard retriever: {len(docs)} doc(s) for query '{query[:80]}'")
        return docs


# ---------------------------------------------------------------------------
# Parent-aware retriever
# ---------------------------------------------------------------------------

class ParentAwareRetriever(BaseRetriever):
    """
    Two-stage retriever:
      1. Search child chunks in ChromaDB (small, high-signal embeddings).
      2. Map each hit's parent_id → parent Document for broader context.

    Falls back to the child chunk when the parent is not found in the store.
    Deduplicates by parent_id so one parent is returned at most once even
    when multiple of its children are top hits.
    
    Supports optional metadata filtering to narrow search scope (e.g., by file_type, source).
    """

    vector_store: VectorStore
    parent_store: dict = Field(default_factory=dict)
    top_k: int = Field(default=6)
    filter_metadata: dict | None = Field(default=None)  # Optional metadata filters

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        # Fetch more child chunks than needed — some may share a parent
        # Apply metadata filter if provided
        if self.filter_metadata:
            logger.debug(f"Applying metadata filter: {self.filter_metadata}")
            child_hits = self.vector_store.similarity_search(
                query, 
                k=self.top_k * 2,
                filter=self.filter_metadata
            )
        else:
            child_hits = self.vector_store.similarity_search(query, k=self.top_k * 2)

        seen_parents: set[str] = set()
        result: list[Document] = []

        for child in child_hits:
            parent_id = child.metadata.get("parent_id")

            if parent_id and parent_id in self.parent_store:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    result.append(self.parent_store[parent_id])
            else:
                # No parent found — use the child itself as context
                chunk_id = child.metadata.get("chunk_id", id(child))
                if chunk_id not in seen_parents:
                    seen_parents.add(chunk_id)
                    result.append(child)

            if len(result) >= self.top_k:
                break

        filter_desc = f" (filtered: {self.filter_metadata})" if self.filter_metadata else ""
        logger.debug(
            f"ParentAwareRetriever: {len(child_hits)} child hits → {len(result)} unique context doc(s) for '{query[:80]}'{filter_desc}"
        )
        return result


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def get_retriever(
    use_parent: bool | None = None,
    top_k: int | None = None,
) -> BaseRetriever:
    """
    Return the configured retriever (singleton cached).

    Args:
        use_parent: True → ParentAwareRetriever.
                    False → StandardRetriever.
                    None  → reads settings.enable_hybrid_search (used as proxy
                            for parent-doc mode; rename env var as needed).
        top_k:      Number of context documents to return. Defaults to
                    settings.retriever_top_k.
    
    NOTE: Retriever is cached after first call. If you change use_parent or
    top_k at runtime, those changes will be ignored (returns cached instance).
    For testing, clear _RETRIEVER_CACHE global before calling.
    """
    global _RETRIEVER_CACHE, _RETRIEVER_BUILD_TIME, _RETRIEVER_CONFIG
    
    # Return cached retriever if already built
    if _RETRIEVER_CACHE is not None:
        logger.debug(f"Retriever cache hit (built {_RETRIEVER_BUILD_TIME:.2f}ms ago)")
        return _RETRIEVER_CACHE
    
    build_start = time.perf_counter()
    
    k = top_k or settings.retriever_top_k
    vector_store = get_langchain_vector_store()

    # Determine mode
    parent_mode = use_parent if use_parent is not None else True
    
    config = {"use_parent": parent_mode, "top_k": k}
    _RETRIEVER_CONFIG = config

    if parent_mode:
        parent_store = _load_parent_store()
        logger.info(f"Building ParentAwareRetriever singleton (top_k={k})")
        _RETRIEVER_CACHE = ParentAwareRetriever(
            vector_store=vector_store,
            parent_store=parent_store,
            top_k=k,
        )
    else:
        logger.info(f"Building StandardRetriever singleton (top_k={k})")
        _RETRIEVER_CACHE = StandardRetriever(vector_store=vector_store, top_k=k)
    
    build_time_ms = (time.perf_counter() - build_start) * 1000
    _RETRIEVER_BUILD_TIME = build_time_ms
    logger.info(f"Retriever singleton cached in {build_time_ms:.2f}ms")
    
    return _RETRIEVER_CACHE


def get_retriever_stats() -> dict[str, Any]:
    """Return retriever caching statistics for monitoring."""
    return {
        "cached": _RETRIEVER_CACHE is not None,
        "build_time_ms": _RETRIEVER_BUILD_TIME,
        "config": _RETRIEVER_CONFIG,
        "parent_store_size": len(_PARENT_STORE_CACHE) if _PARENT_STORE_CACHE else 0,
    }


def create_metadata_filter(
    file_type: str | None = None,
    source: str | None = None,
    file_hash: str | None = None,
) -> dict | None:
    """
    Create a metadata filter dict for retriever queries.
    
    Args:
        file_type: Filter by file type (e.g., 'pdf', 'txt')
        source: Filter by source file path
        file_hash: Filter by file hash
    
    Returns:
        Metadata filter dict compatible with ChromaDB where clause, or None if no filters
        
    Example:
        filter = create_metadata_filter(file_type="pdf", source="/path/to/doc.pdf")
        retriever = get_retriever(filter_metadata=filter)
    """
    filters = {}
    if file_type:
        filters["file_type"] = file_type
    if source:
        filters["source"] = source
    if file_hash:
        filters["file_hash"] = file_hash
    
    return filters if filters else None
