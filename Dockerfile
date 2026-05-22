# =============================================================================
# Enterprise RAG & GenAI Knowledge Base — Dockerfile
# Multi-stage build: builder installs deps, production image is lean.
#
# Build:   docker build -t enterprise-rag .
# Run:     docker run -p 8000:8000 --env-file .env enterprise-rag
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — dependency builder
# Installs all Python packages into /install so the final stage just copies
# the compiled tree without pip, setuptools, or the wheel cache.
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# System libraries needed to *compile* some packages (e.g. tokenizers, magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first — Docker caches this layer until
# requirements.txt changes, making subsequent builds much faster.
COPY requirements.txt .

# Install into an isolated prefix so we can COPY just that tree below.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# -----------------------------------------------------------------------------
# Stage 2 — production runtime
# Minimal image: no build tools, no pip cache, no test code.
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS production

# ── Security: run as non-root ─────────────────────────────────────────────────
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# ── System runtime libraries only (no -dev packages) ─────────────────────────
# libmagic1   → python-magic (MIME detection)
# libgomp1    → PyTorch OpenMP threading
# curl        → Docker HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Copy installed Python packages from builder ───────────────────────────────
COPY --from=builder /install /usr/local

# ── Copy application source ───────────────────────────────────────────────────
COPY app/     ./app/
COPY scripts/ ./scripts/

# ── Create runtime directories and assign ownership ───────────────────────────
RUN mkdir -p \
        data/raw \
        data/processed \
        data/uploads \
        storage/chroma \
        logs \
        .cache/huggingface \
    && chown -R appuser:appuser /app

USER appuser

# ── Environment defaults ──────────────────────────────────────────────────────
# All values can be overridden by docker-compose environment: or --env-file.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Adds /app to sys.path so `import app.xxx` resolves correctly
    PYTHONPATH=/app \
    # Point HuggingFace cache to a volume-backed path so model weights
    # survive container restarts without re-downloading.
    HF_HOME=/app/.cache/huggingface \
    # Prevents a tokenizers warning inside forked/threaded processes.
    TOKENIZERS_PARALLELISM=false

EXPOSE 8000

# ── Health check ──────────────────────────────────────────────────────────────
# start_period gives the container time to download the embedding model on
# first boot (~30-60 s for bge-small-en-v1.5 over a decent connection).
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=90s \
    --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Single worker: ChromaDB PersistentClient is not safe to share across OS
# processes on the same volume. Scale horizontally (multiple containers with
# separate volumes + a read-replica strategy) rather than vertically.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]
