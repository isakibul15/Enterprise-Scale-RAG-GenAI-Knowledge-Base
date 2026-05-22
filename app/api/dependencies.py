"""
FastAPI dependency providers.

All heavy objects are singletons cached at module level.
Dependency functions are trivial — they just return the cached instance —
but wrapping them in Depends() lets us swap implementations in tests via
FastAPI's dependency_overrides mechanism.
"""

from functools import lru_cache

from app.ingestion.pipeline import IngestionPipeline


@lru_cache(maxsize=1)
def get_ingestion_pipeline() -> IngestionPipeline:
    """Return the shared IngestionPipeline (re_ingest=True by default)."""
    return IngestionPipeline(re_ingest=True)
