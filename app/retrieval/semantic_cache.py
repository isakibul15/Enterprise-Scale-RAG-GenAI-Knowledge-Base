"""
Semantic query caching using embeddings.

Cache responses for semantically similar queries.
Uses cosine similarity to identify duplicates with ~90% similarity threshold.
Reduces LLM calls for recurring question patterns.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict
import numpy as np
from scipy.spatial.distance import cosine
from loguru import logger

from app.ingestion.embedder import get_embedding_model


@dataclass
class CachedResponse:
    """Cached query response."""
    query: str
    response: str
    embedding: list[float]
    timestamp: float
    ttl_seconds: int = 3600  # 1 hour default TTL

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return (datetime.now().timestamp() - self.timestamp) > self.ttl_seconds

    def similarity_to(self, other_embedding: list[float]) -> float:
        """Calculate cosine similarity to another query embedding."""
        try:
            return 1 - cosine(self.embedding, other_embedding)
        except Exception as e:
            logger.warning(f"Similarity calculation failed: {e}")
            return 0.0


class SemanticQueryCache:
    """Cache for query-response pairs using semantic similarity."""

    def __init__(self, max_entries: int = 1000, similarity_threshold: float = 0.90):
        self.cache: dict[str, CachedResponse] = {}
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self.embedding_model = None

    def _get_embedding_model(self):
        """Lazy-load embedding model."""
        if self.embedding_model is None:
            self.embedding_model = get_embedding_model()
        return self.embedding_model

    def _get_query_embedding(self, query: str) -> list[float]:
        """Get embedding for a query."""
        try:
            embedder = self._get_embedding_model()
            embeddings = embedder.embed_documents([query])
            return embeddings[0] if embeddings else []
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return []

    def get(self, query: str) -> Optional[str]:
        """
        Retrieve cached response for semantically similar query.
        Returns response if similarity >= threshold, None otherwise.
        """
        query_embedding = self._get_query_embedding(query)
        if not query_embedding:
            return None

        best_match = None
        best_similarity = 0.0

        for cached in self.cache.values():
            if cached.is_expired():
                continue

            similarity = cached.similarity_to(query_embedding)
            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_match = cached

        if best_match:
            logger.debug(
                f"Cache hit! Similarity: {best_similarity:.3f} "
                f"Original: '{best_match.query}' → Requested: '{query}'"
            )
            return best_match.response

        return None

    def set(self, query: str, response: str, ttl_seconds: int = 3600) -> None:
        """Cache a query-response pair."""
        # Remove expired entries to keep cache size manageable
        self.cache = {k: v for k, v in self.cache.items() if not v.is_expired()}

        # Evict oldest entry if cache is full
        if len(self.cache) >= self.max_entries:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].timestamp)
            del self.cache[oldest_key]
            logger.debug(f"Cache full. Evicted oldest entry: {oldest_key}")

        query_embedding = self._get_query_embedding(query)
        if not query_embedding:
            logger.warning("Failed to cache query - no embedding generated")
            return

        cache_key = hashlib.sha256(query.encode()).hexdigest()[:16]
        self.cache[cache_key] = CachedResponse(
            query=query,
            response=response,
            embedding=query_embedding,
            timestamp=datetime.now().timestamp(),
            ttl_seconds=ttl_seconds,
        )

        logger.debug(f"Cached query response. Cache size: {len(self.cache)}/{self.max_entries}")

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logger.info("Semantic query cache cleared")

    def stats(self) -> dict:
        """Get cache statistics."""
        active_entries = sum(1 for v in self.cache.values() if not v.is_expired())
        return {
            "total_entries": len(self.cache),
            "active_entries": active_entries,
            "capacity": self.max_entries,
            "utilization_percent": round((active_entries / self.max_entries) * 100, 2),
            "threshold": self.similarity_threshold,
        }


# Global cache instance
_SEMANTIC_CACHE = SemanticQueryCache(max_entries=1000, similarity_threshold=0.90)


def get_semantic_cache() -> SemanticQueryCache:
    """Get the global semantic query cache."""
    return _SEMANTIC_CACHE
