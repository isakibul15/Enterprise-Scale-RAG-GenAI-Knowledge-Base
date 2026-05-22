"""GET /health — liveness + dependency readiness check."""

from fastapi import APIRouter
from loguru import logger

from app.core.config import settings
from app.models.responses import HealthResponse

router = APIRouter()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the status of the API and its upstream dependencies.",
)
async def health() -> HealthResponse:
    # --- ChromaDB ping ---
    chroma_status = "unavailable"
    try:
        from app.retrieval.vector_store import get_chroma_client
        client = get_chroma_client()
        client.heartbeat()          # raises if the embedded DB is corrupt
        chroma_status = "connected"
    except Exception as exc:
        logger.warning("ChromaDB health check failed: {}", exc)

    # --- Embedding model (check the singleton is initialised) ---
    embed_status = "not_loaded"
    try:
        from app.ingestion.embedder import get_embedding_model
        get_embedding_model()       # returns instantly once warm
        embed_status = "loaded"
    except Exception as exc:
        logger.warning("Embedding model health check failed: {}", exc)

    overall = "ok" if chroma_status == "connected" else "degraded"

    return HealthResponse(
        status=overall,
        chromadb=chroma_status,
        embedding_model=f"{settings.embedding_model} ({embed_status})",
        llm_provider=settings.llm_provider.value,
    )
