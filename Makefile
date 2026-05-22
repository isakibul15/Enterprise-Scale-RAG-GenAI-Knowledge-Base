# =============================================================================
# Makefile — Enterprise RAG & GenAI Knowledge Base
#
# Usage:  make <target>
# Requires: docker, docker compose v2, python 3.11+
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help build up down restart logs shell lint format test \
        pull-model ingest prod-up prod-down clean

# Colours for help output
CYAN  := \033[36m
RESET := \033[0m

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-18s$(RESET) %s\n", $$1, $$2}'

# =============================================================================
# Docker — development (uses docker-compose.override.yml automatically)
# =============================================================================

build:  ## Build the Docker image
	docker compose build --no-cache

up:  ## Start all services in the background (dev mode, hot-reload on)
	docker compose up -d
	@echo ""
	@echo "  API:    http://localhost:8000"
	@echo "  Docs:   http://localhost:8000/docs"
	@echo "  Health: http://localhost:8000/health"
	@echo ""
	@echo "  Run 'make pull-model' if this is your first start."

down:  ## Stop and remove containers (volumes are preserved)
	docker compose down

restart:  ## Restart the rag-api container only
	docker compose restart rag-api

logs:  ## Follow rag-api logs (Ctrl-C to exit)
	docker compose logs -f rag-api

logs-all:  ## Follow logs for all services
	docker compose logs -f

shell:  ## Open a bash shell inside the running rag-api container
	docker compose exec rag-api /bin/bash

# =============================================================================
# Docker — production (explicit file, no override)
# =============================================================================

prod-up:  ## Start in production mode (no hot-reload, resource limits enforced)
	docker compose -f docker-compose.yml up -d

prod-down:  ## Stop production stack
	docker compose -f docker-compose.yml down

# =============================================================================
# Ollama model management
# =============================================================================

pull-model:  ## Pull the default LLM into the Ollama container (run once after first `make up`)
	@MODEL=$$(grep '^LLM_MODEL' .env 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "llama3.1"); \
	echo "Pulling model: $$MODEL"; \
	docker compose exec ollama ollama pull $$MODEL

list-models:  ## List models available in Ollama
	docker compose exec ollama ollama list

# =============================================================================
# Document ingestion
# =============================================================================

ingest:  ## Ingest a file or directory: make ingest path=data/raw/report.pdf
ifndef path
	$(error 'path' is required. Usage: make ingest path=<file-or-dir>)
endif
	docker compose exec rag-api python scripts/ingest_bulk.py --path $(path)

ingest-dry:  ## Dry-run ingestion (no Qdrant write): make ingest-dry path=data/raw/
ifndef path
	$(error 'path' is required. Usage: make ingest-dry path=<file-or-dir>)
endif
	docker compose exec rag-api python scripts/ingest_bulk.py --path $(path) --dry-run

# =============================================================================
# Local development (without Docker)
# =============================================================================

install:  ## Install production + dev dependencies in the active virtualenv
	pip install -r requirements-dev.txt

test:  ## Run the full test suite with coverage
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

test-unit:  ## Run only unit tests (fast, no I/O)
	pytest tests/unit/ -v

test-integration:  ## Run integration tests
	pytest tests/integration/ -v

lint:  ## Run ruff linter and mypy type checker
	ruff check app/ tests/ scripts/
	mypy app/ --ignore-missing-imports

format:  ## Auto-format with black and fix ruff issues
	black app/ tests/ scripts/
	ruff check app/ tests/ scripts/ --fix

run-local:  ## Run the API locally (outside Docker) with hot-reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# =============================================================================
# Housekeeping
# =============================================================================

clean:  ## Remove containers AND named volumes (WARNING: deletes all vector data)
	@echo "This will delete all ChromaDB data, uploads, and model cache."
	@read -p "Are you sure? [y/N] " ans && [ "$$ans" = "y" ] || exit 0
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

clean-build:  ## Remove Docker build cache
	docker builder prune -f
