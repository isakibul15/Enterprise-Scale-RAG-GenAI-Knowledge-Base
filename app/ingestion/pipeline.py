"""
Ingestion pipeline orchestrator.

Full flow per file:
  load_file → split → delete_old_chunks (if re-ingesting) → upsert_children

Parent chunks are serialised to a local JSON docstore so the
ParentDocumentRetriever in Milestone 3 can reconstruct full context.

The pipeline is intentionally synchronous so it can be run from a
CLI script or handed off to a background worker (Celery, ARQ, etc.).

Supports parallel batch processing with ThreadPoolExecutor for multi-file ingestion.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from app.ingestion.loader import load_directory, load_file
from app.ingestion.splitter import DocumentSplitter
from app.retrieval.vector_store import delete_by_source, upsert_documents

# JSON file used as a lightweight parent-chunk docstore (Milestone 3 reads this)
_PARENT_STORE_PATH = Path("data/processed/parent_store.json")

# JSON file tracking file hashes to skip re-embedding unchanged files
_FILE_HASH_REGISTRY_PATH = Path("data/processed/file_hash_registry.json")

# Parallel processing configuration
_MAX_WORKERS = 4  # Number of parallel threads for file ingestion
_PARALLEL_ENABLED = True  # Enable/disable parallel processing


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IngestionResult:
    total_files: int = 0
    successful_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    total_child_chunks: int = 0
    total_parent_chunks: int = 0
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return len(self.successful_files) / self.total_files * 100

    def log_summary(self) -> None:
        logger.info(
            "Ingestion complete | files: {}/{} ok | "
            "child chunks: {} | parent chunks: {} | {:.1f}s",
            len(self.successful_files),
            self.total_files,
            self.total_child_chunks,
            self.total_parent_chunks,
            self.duration_seconds,
        )
        if self.failed_files:
            logger.warning("Failed files: {}", self.failed_files)


# ---------------------------------------------------------------------------
# Parent docstore helpers (cached singleton to avoid repeated file I/O)
# ---------------------------------------------------------------------------

_PARENT_STORE_CACHE: dict | None = None


def get_parent_store() -> dict:
    """
    Return the cached parent store.
    
    Loads from disk on first call and caches in memory.
    Use this instead of _load_parent_store() to avoid repeated I/O.
    """
    global _PARENT_STORE_CACHE
    if _PARENT_STORE_CACHE is None:
        logger.info("Loading parent store from disk…")
        _PARENT_STORE_CACHE = _load_parent_store()
        logger.info("Parent store loaded: {} entries", len(_PARENT_STORE_CACHE))
    return _PARENT_STORE_CACHE


def _load_parent_store() -> dict:
    """Load parent store from disk (internal)."""
    if _PARENT_STORE_PATH.exists():
        with _PARENT_STORE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_parent_store(store: dict) -> None:
    """Save parent store to disk and update cache."""
    global _PARENT_STORE_CACHE
    _PARENT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _PARENT_STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    # Invalidate cache so next access reloads
    _PARENT_STORE_CACHE = store


def _load_file_hash_registry() -> dict:
    """Load file hash registry from disk (internal). Format: {source_path: file_hash}"""
    if _FILE_HASH_REGISTRY_PATH.exists():
        with _FILE_HASH_REGISTRY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_file_hash_registry(registry: dict) -> None:
    """Save file hash registry to disk."""
    _FILE_HASH_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FILE_HASH_REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def is_file_already_ingested(source_path: str, file_hash: str) -> bool:
    """Check if a file with the same hash has already been ingested. Skip if yes."""
    registry = _load_file_hash_registry()
    return registry.get(source_path) == file_hash


def register_ingested_file(source_path: str, file_hash: str) -> None:
    """Register a file as ingested by storing its hash."""
    registry = _load_file_hash_registry()
    registry[source_path] = file_hash
    _save_file_hash_registry(registry)


# ---------------------------------------------------------------------------
# Retry decorator for transient errors (network, GPU OOM spikes, etc.)
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type((RuntimeError, ConnectionError)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _upsert_with_retry(child_chunks, collection_name):
    return upsert_documents(child_chunks, collection_name=collection_name)


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------

class IngestionPipeline:
    """
    Orchestrates the full load → split → embed → upsert pipeline.

    Args:
        collection_name: Override the default ChromaDB collection.
        re_ingest: If True, delete existing chunks for a source before upserting.
        child_chunk_size: Override settings.chunk_size.
        child_chunk_overlap: Override settings.chunk_overlap.
        batch_size: Number of child chunks per ChromaDB upsert call.
    """

    def __init__(
        self,
        collection_name: str | None = None,
        re_ingest: bool = True,
        child_chunk_size: int | None = None,
        child_chunk_overlap: int | None = None,
        batch_size: int = 64,
    ) -> None:
        self._collection = collection_name
        self._re_ingest = re_ingest
        self._batch_size = batch_size
        self._splitter = DocumentSplitter(
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ingest_file(self, file_path: Path) -> IngestionResult:
        """Ingest a single file. Returns an IngestionResult."""
        result = IngestionResult(total_files=1)
        t0 = time.perf_counter()

        try:
            self._process_file(file_path, result)
        except Exception as exc:
            logger.error("Failed to ingest '{}': {}", file_path.name, exc)
            result.failed_files.append(str(file_path))

        result.duration_seconds = time.perf_counter() - t0
        result.log_summary()
        return result

    def ingest_directory(
        self,
        dir_path: Path,
        recursive: bool = True,
    ) -> IngestionResult:
        """Ingest every supported file under *dir_path* with optional parallelization."""
        result = IngestionResult()
        t0 = time.perf_counter()

        file_iter = list(load_directory(dir_path, recursive=recursive))
        result.total_files = len(file_iter)

        if _PARALLEL_ENABLED and len(file_iter) > 1:
            # Use ThreadPoolExecutor for parallel ingestion
            logger.info(f"Starting parallel ingestion with {_MAX_WORKERS} workers")
            self._ingest_directory_parallel(file_iter, result)
        else:
            # Sequential ingestion for small batches or disabled parallelization
            for file_path, docs in tqdm(file_iter, desc="Ingesting files", unit="file"):
                try:
                    self._process_docs(file_path, docs, result)
                except Exception as exc:
                    logger.error(f"Failed to ingest '{file_path.name}': {exc}")
                    result.failed_files.append(str(file_path))

        result.duration_seconds = time.perf_counter() - t0
        result.log_summary()
        return result

    def _ingest_directory_parallel(self, file_iter, result: IngestionResult) -> None:
        """Process multiple files in parallel using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            # Submit all tasks
            futures = {}
            for file_path, docs in file_iter:
                future = executor.submit(self._process_docs_safe, file_path, docs, result)
                futures[future] = str(file_path)
            
            # Process completed tasks with progress bar
            with tqdm(total=len(futures), desc="Ingesting files (parallel)", unit="file") as pbar:
                for future in as_completed(futures):
                    file_path_str = futures[future]
                    try:
                        future.result()
                        logger.debug(f"Completed parallel ingestion: {file_path_str}")
                    except Exception as exc:
                        logger.error(f"Failed to ingest '{file_path_str}' (parallel): {exc}")
                        result.failed_files.append(file_path_str)
                    finally:
                        pbar.update(1)

    def _process_docs_safe(self, file_path: Path, docs, result: IngestionResult) -> None:
        """Thread-safe wrapper for _process_docs with proper result accumulation."""
        try:
            source = str(file_path.resolve())
            file_hash = docs[0].metadata.get("file_hash", "")
            if is_file_already_ingested(source, file_hash):
                logger.info(f"File '{file_path.name}' already ingested (hash match) — skipping")
                result.successful_files.append(source)
                return
            
            self._process_docs(file_path, docs, result)
        except Exception as exc:
            logger.error(f"Error in parallel processing: {exc}")
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_file(self, file_path: Path, result: IngestionResult) -> None:
        """Load a file and hand its documents to _process_docs."""
        docs = load_file(file_path)
        if not docs:
            logger.warning("No content extracted from '{}' — skipping", file_path.name)
            result.failed_files.append(str(file_path))
            return
        
        # Check if file has already been ingested with same hash (deduplication)
        source = str(file_path.resolve())
        file_hash = docs[0].metadata.get("file_hash", "")
        if is_file_already_ingested(source, file_hash):
            logger.info("File '{}' already ingested (hash match) — skipping", file_path.name)
            result.successful_files.append(source)  # Count as successful but skip processing
            return
        
        self._process_docs(file_path, docs, result)

    def _process_docs(self, file_path: Path, docs, result: IngestionResult) -> None:
        """Split → optionally purge → upsert child chunks, persist parent chunks."""
        source = str(file_path.resolve())

        # --- chunk ---
        split = self._splitter.split(docs)
        if not split.child_chunks:
            logger.warning("No child chunks produced for '{}' — skipping", file_path.name)
            result.failed_files.append(source)
            return

        # --- purge old vectors for this source (idempotent re-ingest) ---
        if self._re_ingest:
            delete_by_source(source, collection_name=self._collection)

        # --- upsert children into ChromaDB ---
        _upsert_with_retry(split.child_chunks, self._collection)

        # --- persist parent chunks to local JSON docstore ---
        parent_store = get_parent_store()
        for parent in split.parent_chunks:
            pid = parent.metadata["chunk_id"]
            parent_store[pid] = {
                "page_content": parent.page_content,
                "metadata": parent.metadata,
            }
        _save_parent_store(parent_store)

        # --- register file hash to skip re-ingestion of unchanged files ---
        file_hash = docs[0].metadata.get("file_hash", "")
        register_ingested_file(source, file_hash)

        result.successful_files.append(source)
        result.total_child_chunks += len(split.child_chunks)
        result.total_parent_chunks += len(split.parent_chunks)

        logger.info(
            "'{}': {} child chunk(s), {} parent chunk(s) upserted",
            file_path.name,
            len(split.child_chunks),
            len(split.parent_chunks),
        )
