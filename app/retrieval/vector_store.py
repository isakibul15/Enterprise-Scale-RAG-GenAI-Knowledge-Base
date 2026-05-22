"""
Qdrant vector store wrapper.

Handles:
  - Client creation (local on-disk or remote server)
  - Collection bootstrap with correct vector schema
  - Idempotent upsert of LangChain Documents
  - Delete-by-source for re-ingestion workflows
  - LangChain-compatible QdrantVectorStore accessor for Milestone 3

Design: keeps a single QdrantClient per process (module-level singleton).
"""

from functools import lru_cache
from typing import Any

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings, QdrantMode
from app.ingestion.embedder import get_embedding_dimension, get_embedding_model

# Qdrant payload field used to store the raw document text
CONTENT_FIELD = "page_content"


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Return the process-level Qdrant client (local or server)."""
    if settings.qdrant_mode == QdrantMode.local:
        settings.qdrant_local_path.mkdir(parents=True, exist_ok=True)
        logger.info("Qdrant: on-disk mode at '{}'", settings.qdrant_local_path)
        return QdrantClient(path=str(settings.qdrant_local_path))

    logger.info(
        "Qdrant: server mode at {}:{}",
        settings.qdrant_host,
        settings.qdrant_port,
    )
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=30,
    )


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
) -> None:
    """
    Create the Qdrant collection if it does not already exist.

    Uses cosine distance — correct for normalized BGE embeddings.
    Idempotent: safe to call on every startup.
    """
    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        logger.info("Collection '{}' already exists — skipping creation", collection_name)
        return

    logger.info(
        "Creating collection '{}' (dim={}, metric=Cosine)",
        collection_name,
        vector_size,
    )
    client.create_collection(
        collection_name=collection_name,
        vectors_config=qmodels.VectorParams(
            size=vector_size,
            distance=qmodels.Distance.COSINE,
            on_disk=True,           # offload vectors to disk, keeps RAM lean
        ),
        optimizers_config=qmodels.OptimizersConfigDiff(
            indexing_threshold=20_000,  # build HNSW only after 20k vectors
        ),
        hnsw_config=qmodels.HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
    )
    logger.info("Collection '{}' created successfully", collection_name)


def upsert_documents(
    documents: list[Document],
    collection_name: str | None = None,
    batch_size: int = 64,
) -> int:
    """
    Embed and upsert *documents* into Qdrant.

    Uses the chunk_id stored in document metadata as the Qdrant point ID so
    re-ingesting the same content is idempotent (upsert semantics).

    Returns the number of points successfully upserted.
    """
    if not documents:
        return 0

    coll = collection_name or settings.qdrant_collection_name
    client = get_qdrant_client()
    embed_model = get_embedding_model()

    ensure_collection(client, coll, get_embedding_dimension())

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

        points = [
            qmodels.PointStruct(
                id=doc.metadata["chunk_id"],
                vector=vector,
                payload={
                    CONTENT_FIELD: doc.page_content,
                    **doc.metadata,
                },
            )
            for doc, vector in zip(batch_docs, vectors)
        ]

        try:
            client.upsert(collection_name=coll, points=points, wait=True)
            total_upserted += len(points)
            logger.debug(
                "Upserted batch [{}-{}] ({} points)",
                batch_start,
                batch_start + len(points),
                len(points),
            )
        except UnexpectedResponse as exc:
            logger.error("Qdrant upsert failed: {}", exc)
            raise

    logger.info(
        "Upserted {} point(s) into collection '{}'",
        total_upserted,
        coll,
    )
    return total_upserted


def delete_by_source(source_path: str, collection_name: str | None = None) -> int:
    """
    Delete all points whose `source` payload matches *source_path*.

    Used when re-ingesting an updated file — purge old chunks first.
    Returns the number of points deleted.
    """
    coll = collection_name or settings.qdrant_collection_name
    client = get_qdrant_client()

    result = client.delete(
        collection_name=coll,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="source",
                        match=qmodels.MatchValue(value=source_path),
                    )
                ]
            )
        ),
        wait=True,
    )
    logger.info("Deleted points for source '{}': {}", source_path, result)
    return 0  # Qdrant delete result doesn't expose a count directly


@lru_cache(maxsize=1)
def get_langchain_vector_store(
    collection_name: str | None = None,
) -> QdrantVectorStore:
    """
    Return a LangChain-compatible QdrantVectorStore.

    Used by the retriever and QA chain in Milestone 3.
    Cached — same object reused across requests.
    """
    coll = collection_name or settings.qdrant_collection_name
    client = get_qdrant_client()
    embed_model = get_embedding_model()

    ensure_collection(client, coll, get_embedding_dimension())

    return QdrantVectorStore(
        client=client,
        collection_name=coll,
        embedding=embed_model,
        content_payload_key=CONTENT_FIELD,
    )
