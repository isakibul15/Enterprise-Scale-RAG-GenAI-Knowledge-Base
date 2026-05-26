"""
Embedding model singleton.

Uses HuggingFaceEmbeddings (sentence-transformers backend).
BGE models require normalize_embeddings=True for cosine similarity to be meaningful.
The singleton is lazy-loaded on first access to avoid GPU/CPU allocation at import time.

Supports batch embedding with parallel processing for faster ingestion.
"""

import asyncio
from functools import lru_cache
from typing import AsyncIterator

from langchain_huggingface import HuggingFaceEmbeddings
from loguru import logger

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Return the cached embedding model.

    First call downloads the model weights (if not already cached by HuggingFace Hub)
    and warms up the encoder. Subsequent calls return the same object instantly.

    Raises:
        RuntimeError: If model loading fails.
    """
    try:
        logger.info(
            "Loading embedding model '{}' on device '{}'",
            settings.embedding_model,
            settings.embedding_device,
        )

        model = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": settings.embedding_device},
            encode_kwargs={
                "batch_size": settings.embedding_batch_size,
                # normalize_embeddings=True is required for BGE and most bi-encoders
                # so that cosine similarity == dot product (faster ChromaDB search)
                "normalize_embeddings": True,
                # show_progress_bar is intentionally omitted — langchain_huggingface
                # already passes it internally to encode(); including it here raises
                # "multiple values for keyword argument 'show_progress_bar'"
            },
            cache_folder=".cache/sentence_transformers",
        )

        # Warm-up pass + dimension probe (avoids cold-start latency on first real query)
        sample = model.embed_query("warm-up")
        logger.info(
            "Embedding model ready — vector dimension: {}",
            len(sample),
        )
        return model
    except Exception as e:
        logger.error("Failed to load embedding model: {}", str(e))
        raise RuntimeError(f"Embedding model initialization failed: {e}") from e


def get_embedding_dimension() -> int:
    """
    Return the output vector size of the loaded model.

    Raises:
        RuntimeError: If dimension detection fails.
    """
    try:
        model = get_embedding_model()
        dimension = len(model.embed_query("dim-probe"))
        return dimension
    except Exception as e:
        logger.error("Failed to detect embedding dimension: {}", str(e))
        raise RuntimeError(f"Embedding dimension detection failed: {e}") from e


async def embed_documents_parallel(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """
    Embed a list of texts in parallel batches for faster ingestion.
    
    Args:
        texts: List of text documents to embed.
        batch_size: Batch size for parallel processing. Defaults to settings.embedding_batch_size.
    
    Returns:
        List of embedding vectors.
    """
    model = get_embedding_model()
    if batch_size is None:
        batch_size = settings.embedding_batch_size
    
    # Process in parallel batches using asyncio + thread pool
    def embed_batch(batch: list[str]) -> list[list[float]]:
        return model.embed_documents(batch)
    
    loop = asyncio.get_event_loop()
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    
    logger.info("Parallel embedding: {} texts in {} batches", len(texts), len(batches))
    
    # Run all batches in parallel using thread pool executor
    tasks = [loop.run_in_executor(None, embed_batch, batch) for batch in batches]
    results = await asyncio.gather(*tasks)
    
    # Flatten results from batches
    embeddings = []
    for batch_result in results:
        embeddings.extend(batch_result)
    
    logger.info("Parallel embedding complete: {} vectors generated", len(embeddings))
    return embeddings
