"""
Embedding model singleton.

Uses HuggingFaceEmbeddings (sentence-transformers backend).
BGE models require normalize_embeddings=True for cosine similarity to be meaningful.
The singleton is lazy-loaded on first access to avoid GPU/CPU allocation at import time.
"""

from functools import lru_cache

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
