"""
FastAPI application factory and lifespan manager.

Startup sequence
----------------
1. Configure structured logging (Loguru).
2. Warm up the embedding model — downloads weights on first run, caches locally.
   Done in a thread so the event loop stays responsive.
3. Ensure the ChromaDB collection exists (idempotent).

Shutdown
--------
ChromaDB PersistentClient flushes to disk automatically; no explicit close needed.

Route layout
------------
GET  /health
POST /upload
POST /query
POST /query/stream
DELETE /query/session/{session_id}
GET  /query/sessions
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.middleware.logging import RequestLoggingMiddleware
from app.api.middleware.performance import PerformanceMonitoringMiddleware
from app.api.routes import health, query, upload
from app.core.config import settings
from app.core.logging import configure_logging


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    configure_logging()
    logger.info(
        "Starting Enterprise RAG | env={} | embed={} | llm={}/{}",
        settings.app_env,
        settings.embedding_model,
        settings.llm_provider,
        settings.llm_model,
    )

    # Warm up embedding model in a thread (avoids blocking the event loop
    # during the potentially slow first-time model download / load)
    logger.info("Warming up embedding model…")
    await asyncio.to_thread(_warm_up)
    logger.info("Startup complete — API is ready")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down — goodbye")


def _warm_up() -> None:
    """Initialise all singletons eagerly so the first real request is fast."""
    from app.ingestion.embedder import get_embedding_model
    from app.retrieval.vector_store import get_langchain_vector_store

    get_embedding_model()          # downloads + loads model weights
    get_langchain_vector_store()   # creates ChromaDB collection if absent


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise RAG & GenAI Knowledge Base",
        description=(
            "Production-grade Retrieval-Augmented Generation API. "
            "Upload documents, ask questions, get grounded answers with citations."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware (applied in reverse registration order) ────────────────────

    # 1. CORS — allow all origins in dev; tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Performance monitoring — tracks latencies, cache hits, endpoint stats
    app.add_middleware(PerformanceMonitoringMiddleware)

    # 3. Request logging + X-Request-ID injection
    app.add_middleware(RequestLoggingMiddleware)

    # ── Global exception handlers ─────────────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning("Validation error on {} {}: {}", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": exc.errors(),
                "error_code": "VALIDATION_ERROR",
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled {} on {} {}", type(exc).__name__, request.method, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred.",
                "error_code": "INTERNAL_SERVER_ERROR",
            },
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(upload.router, prefix="/upload", tags=["Ingestion"])
    app.include_router(query.router, prefix="/query", tags=["Retrieval"])

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "Enterprise RAG API — visit /docs for the interactive UI."}

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Dev entrypoint:  python -m app.main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env.value == "development",
        log_level=settings.log_level.lower(),
    )
