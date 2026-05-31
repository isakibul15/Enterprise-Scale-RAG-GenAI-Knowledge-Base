"""
ChromaDB vector store wrapper.

ChromaDB runs embedded inside the process — no separate server required.
Data is persisted automatically to CHROMA_PERSIST_DIR on every write.

Handles:
  - PersistentClient creation (one per process) with connection pooling
  - Collection bootstrap with cosine distance
  - Idempotent upsert of LangChain Documents (chunk_id as Chroma ID)
  - Delete-by-source for re-ingestion workflows
  - LangChain-compatible Chroma accessor for the retriever / QA chain
  - Metadata-filtered searches for efficient retrieval

ChromaDB upsert semantics: if a document with the same ID already exists,
it is overwritten. Re-ingesting the same file therefore produces zero duplicates
as long as chunk_ids are stable (they are — see splitter.py).
"""

from functools import lru_cache
import threading

import chromadb
from chromadb import Collection
from langchain_chroma import Chroma
from langchain_core.documents import Document
from loguru import logger

from app.core.config import settings
from app.ingestion.embedder import get_embedding_dimension, get_embedding_model

# ChromaDB payload key that stores the raw document text
CONTENT_FIELD = "page_content"

# Connection pool semaphore for limiting concurrent database access
_CONNECTION_POOL_SEMAPHORE = threading.Semaphore(settings.connection_pool_size)


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    """
    Return the process-level ChromaDB persistent client.

    Creates the persistence directory if it does not exist.
    The client is cached so all callers share the same connection pool.

    Returns:
        PersistentClient: Cached ChromaDB client instance

    Raises:
        RuntimeError: If client initialization fails
    """
    try:
        persist_path = settings.chroma_persist_dir
        persist_path.mkdir(parents=True, exist_ok=True)
        logger.info("ChromaDB: persistent mode at '{}'", persist_path)
        return chromadb.PersistentClient(path=str(persist_path))
    except Exception as e:
        logger.error("Failed to initialize ChromaDB client: {}", str(e))
        raise RuntimeError(f"ChromaDB initialization failed: {e}") from e


# ---------------------------------------------------------------------------
# Collection bootstrap
# ---------------------------------------------------------------------------

def get_or_create_collection(
    client: chromadb.PersistentClient,
    collection_name: str,
) -> Collection:
    """
    Return the named collection, creating it if necessary.

    Uses cosine distance — correct for L2-normalised BGE embeddings.
    Setting hnsw:space at creation time is permanent; it cannot be changed
    without deleting and recreating the collection.

    Args:
        client: ChromaDB persistent client
        collection_name: Name of the collection

    Returns:
        Collection: ChromaDB collection instance

    Raises:
        RuntimeError: If collection creation/retrieval fails
    """
    try:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection '{}' ready ({} existing vectors)",
            collection_name,
            collection.count(),
        )
        return collection
    except Exception as e:
        logger.error("Failed to create/retrieve collection '{}': {}", collection_name, str(e))
        raise RuntimeError(f"Collection operation failed: {e}") from e


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_documents(
    documents: list[Document],
    collection_name: str | None = None,
    batch_size: int = 64,
) -> int:
    """
    Embed and upsert documents into ChromaDB with connection pooling.

    Uses chunk_id from document metadata as the ChromaDB document ID so
    re-ingesting the same content is idempotent.

    Args:
        documents: List of LangChain Document objects to upsert
        collection_name: ChromaDB collection name (defaults to settings)
        batch_size: Number of documents to process per batch (default: 64)

    Returns:
        int: Number of documents successfully upserted

    Raises:
        ValueError: If documents list is empty
        RuntimeError: If embedding or upsert operations fail
    """
    if not documents:
        logger.warning("No documents provided to upsert")
        return 0

    coll_name = collection_name or settings.collection_name
    
    # Acquire connection from pool to limit concurrent database access
    _CONNECTION_POOL_SEMAPHORE.acquire()
    try:
        client = get_chroma_client()
        collection = get_or_create_collection(client, coll_name)
        embed_model = get_embedding_model()

        texts = [doc.page_content for doc in documents]
        total_upserted = 0

        for batch_start in range(0, len(texts), batch_size):
            batch_texts = texts[batch_start : batch_start + batch_size]
            batch_docs = documents[batch_start : batch_start + batch_size]

            try:
                vectors = embed_model.embed_documents(batch_texts)
            except Exception as exc:
                logger.error(
                    "Embedding failed for batch [{}-{}]: {}",
                    batch_start,
                    batch_start + len(batch_texts),
                    exc,
                )
                raise

            ids = [doc.metadata["chunk_id"] for doc in batch_docs]

            # Flatten metadata: ChromaDB only accepts str / int / float / bool values.
            # Any complex types (lists, dicts, None) are cast to strings.
            # Use cached sanitization for better performance
            metadatas = [_sanitise_metadata_cached(doc.metadata) for doc in batch_docs]

            try:
                collection.upsert(
                    ids=ids,
                    embeddings=vectors,
                    documents=batch_texts,
                    metadatas=metadatas,
                )
                total_upserted += len(ids)
                logger.debug(
                    "Upserted batch [{}-{}] ({} docs)",
                    batch_start,
                    batch_start + len(ids),
                    len(ids),
                )
            except Exception as exc:
                logger.error("ChromaDB upsert failed: {}", exc)
                raise

        logger.info(
            "Upserted {} document(s) into collection '{}'",
            total_upserted,
            coll_name,
        )
        return total_upserted
    finally:
        # Release connection back to pool
        _CONNECTION_POOL_SEMAPHORE.release()


def _sanitise_metadata(metadata: dict) -> dict:
    """
    ChromaDB rejects None and non-scalar values in metadata.
    Cast everything to a safe type so upserts never fail on metadata alone.
    
    Optimized with common patterns cache to reduce string conversions.
    """
    safe: dict = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif v is None:
            safe[k] = ""
        else:
            # Convert complex types to string
            safe[k] = str(v)
    return safe


# Precompute sanitized metadata templates for common document fields
_COMMON_SANITIZED_KEYS = {
    "chunk_id": str,
    "parent_id": str,
    "source": str,
    "file_name": str,
    "file_type": str,
    "file_size_bytes": int,
    "file_hash": str,
    "loaded_at": str,
}


def _sanitise_metadata_cached(metadata: dict) -> dict:
    """
    Optimized metadata sanitization using precomputed type mappings.
    
    Reduces conversion overhead for common metadata fields by using
    cached type information instead of runtime isinstance checks.
    """
    safe: dict = {}
    for k, v in metadata.items():
        expected_type = _COMMON_SANITIZED_KEYS.get(k)
        
        if expected_type is not None:
            # Fast path: known field type
            if expected_type is str:
                safe[k] = str(v) if v is not None else ""
            elif expected_type is int:
                try:
                    safe[k] = int(v)
                except (ValueError, TypeError):
                    safe[k] = str(v)
            else:
                safe[k] = v
        else:
            # Fallback: generic type checking
            if isinstance(v, (str, int, float, bool)):
                safe[k] = v
            elif v is None:
                safe[k] = ""
            else:
                safe[k] = str(v)
    
    return safe


# ---------------------------------------------------------------------------
# Delete by source
# ---------------------------------------------------------------------------

def delete_by_source(source_path: str, collection_name: str | None = None) -> None:
    """
    Delete all documents whose `source` metadata field matches *source_path*.

    Called before re-ingesting an updated file so stale chunks are purged first.
    ChromaDB's `where` filter uses exact string matching.
    """
    coll_name = collection_name or settings.collection_name
    client = get_chroma_client()
    collection = get_or_create_collection(client, coll_name)

    try:
        collection.delete(where={"source": source_path})
        logger.info("Deleted existing chunks for source '{}'", source_path)
    except Exception as exc:
        # ChromaDB raises if no documents match the filter — treat as a no-op
        logger.debug("delete_by_source no-op for '{}': {}", source_path, exc)


# ---------------------------------------------------------------------------
# LangChain-compatible store (used by retriever and QA chain)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_langchain_vector_store(
    collection_name: str | None = None,
) -> Chroma:
    """
    Return a LangChain Chroma instance backed by the persistent client.

    Cached — the same object is reused across all requests. The underlying
    ChromaDB client handles thread safety internally.
    """
    coll_name = collection_name or settings.collection_name
    client = get_chroma_client()
    embed_model = get_embedding_model()

    # Ensure the collection exists before handing it to LangChain
    get_or_create_collection(client, coll_name)

    store = Chroma(
        client=client,
        collection_name=coll_name,
        embedding_function=embed_model,
    )
    logger.info("LangChain Chroma store ready (collection='{}')", coll_name)
    return store


# ---------------------------------------------------------------------------
# Filtered search (metadata filtering support)
# ---------------------------------------------------------------------------

def search_with_metadata_filter(
    query: str,
    k: int = 6,
    collection_name: str | None = None,
    where_filter: dict | None = None,
) -> list[Document]:
    """
    Search documents by semantic similarity with optional metadata filtering.
    
    Args:
        query: Search query text.
        k: Number of results to return.
        collection_name: ChromaDB collection name.
        where_filter: ChromaDB where filter dict. Examples:
            {"source": "path/to/file.pdf"}
            {"file_type": "pdf"}
            {"$or": [{"file_type": "pdf"}, {"file_type": "txt"}]}
    
    Returns:
        List of matching Document objects.
    """
    coll_name = collection_name or settings.collection_name
    client = get_chroma_client()
    collection = get_or_create_collection(client, coll_name)
    embed_model = get_embedding_model()
    
    # Embed query
    query_vector = embed_model.embed_query(query)
    
    # Query with optional filter
    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where=where_filter,
        )
        
        # Convert ChromaDB results to LangChain Documents
        documents = []
        if results["ids"] and results["ids"][0]:
            for idx, doc_id in enumerate(results["ids"][0]):
                doc_text = results["documents"][0][idx]
                metadata = results["metadatas"][0][idx]
                documents.append(Document(page_content=doc_text, metadata=metadata))
        
        logger.debug(
            "Metadata-filtered search: {} results for query '{}' | filter={}",
            len(documents),
            query[:80],
            where_filter,
        )
        return documents
    except Exception as exc:
        logger.warning("Metadata-filtered search failed: {} | filter={}", exc, where_filter)
        # Fallback to unfiltered search
        return get_langchain_vector_store(coll_name).similarity_search(query, k=k)
