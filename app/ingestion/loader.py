"""
Multi-format document loader.

Supported formats: PDF, DOCX, TXT, Markdown, HTML, CSV.
Falls back to UnstructuredFileLoader for unknown types.
Each loaded Document carries rich metadata for downstream filtering.
"""

import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from langchain_community.document_loaders import (
    CSVLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredFileLoader,
    UnstructuredHTMLLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_core.documents import Document
from loguru import logger

# Maps file extensions → loader factory callables
_LOADER_MAP: dict[str, type] = {
    ".pdf": PyPDFLoader,
    ".docx": UnstructuredWordDocumentLoader,
    ".doc": UnstructuredWordDocumentLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".markdown": TextLoader,
    ".html": UnstructuredHTMLLoader,
    ".htm": UnstructuredHTMLLoader,
    ".csv": CSVLoader,
}

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}

# File hash cache database
_HASH_CACHE_DB_PATH = Path("data/processed/.file_hash_cache.db")
_HASH_CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# In-memory cache for hash lookups (reduces DB hits)
_HASH_MEMORY_CACHE: dict[str, tuple[str, float]] = {}  # filepath -> (hash, mtime)


def _init_hash_cache_db() -> None:
    """Initialize SQLite database for file hash caching."""
    try:
        conn = sqlite3.connect(str(_HASH_CACHE_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_hashes (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                file_mtime REAL NOT NULL,
                cached_at REAL NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON file_hashes(file_path)")
        conn.commit()
        conn.close()
        logger.debug(f"File hash cache database initialized at {_HASH_CACHE_DB_PATH}")
    except Exception as e:
        logger.warning(f"Failed to initialize file hash cache DB: {e}")


def _get_cached_hash(file_path: Path) -> str | None:
    """
    Retrieve cached hash if file hasn't been modified.
    
    Returns None if:
    - File not in cache
    - File has been modified since cache entry
    - Cache lookup fails
    """
    file_path_str = str(file_path.resolve())
    
    # Check memory cache first
    if file_path_str in _HASH_MEMORY_CACHE:
        cached_hash, cached_mtime = _HASH_MEMORY_CACHE[file_path_str]
        current_mtime = file_path.stat().st_mtime
        if current_mtime == cached_mtime:
            return cached_hash
        else:
            # File was modified, invalidate memory cache entry
            del _HASH_MEMORY_CACHE[file_path_str]
    
    # Check SQLite cache
    try:
        conn = sqlite3.connect(str(_HASH_CACHE_DB_PATH))
        cursor = conn.cursor()
        current_mtime = file_path.stat().st_mtime
        cursor.execute(
            "SELECT file_hash FROM file_hashes WHERE file_path = ? AND file_mtime = ?",
            (file_path_str, current_mtime)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            cached_hash = row[0]
            # Update memory cache
            _HASH_MEMORY_CACHE[file_path_str] = (cached_hash, current_mtime)
            return cached_hash
    except Exception as e:
        logger.warning(f"Failed to query hash cache: {e}")
    
    return None


def _cache_hash(file_path: Path, file_hash: str) -> None:
    """Store computed hash in cache."""
    file_path_str = str(file_path.resolve())
    current_mtime = file_path.stat().st_mtime
    
    # Update memory cache
    _HASH_MEMORY_CACHE[file_path_str] = (file_hash, current_mtime)
    
    # Update SQLite cache
    try:
        conn = sqlite3.connect(str(_HASH_CACHE_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO file_hashes 
               (file_path, file_hash, file_mtime, cached_at) 
               VALUES (?, ?, ?, ?)""",
            (file_path_str, file_hash, current_mtime, time.time())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to cache hash in DB: {e}")


def _build_loader(file_path: Path):
    """Instantiate the correct loader with sane defaults."""
    ext = file_path.suffix.lower()
    loader_cls = _LOADER_MAP.get(ext, UnstructuredFileLoader)

    if loader_cls is TextLoader:
        return loader_cls(str(file_path), encoding="utf-8", autodetect_encoding=True)
    if loader_cls is CSVLoader:
        return loader_cls(str(file_path), encoding="utf-8")

    return loader_cls(str(file_path))


def _enrich_metadata(doc: Document, file_path: Path, file_hash: str) -> Document:
    """Attach provenance metadata to every Document."""
    stat = file_path.stat()
    doc.metadata.update(
        {
            "source": str(file_path.resolve()),
            "file_name": file_path.name,
            "file_type": file_path.suffix.lower().lstrip("."),
            "file_size_bytes": stat.st_size,
            "file_hash": file_hash,
            "loaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return doc


def _sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_file(file_path: Path) -> list[Document]:
    """
    Load a single file and return enriched LangChain Documents.

    Raises:
        FileNotFoundError: if the path does not exist.
        ValueError: if the file is empty.
        RuntimeError: wraps loader-level errors with context.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.stat().st_size == 0:
        raise ValueError(f"File is empty: {file_path}")

    logger.info(f"Loading file: {file_path.name}")

    # Try to get hash from cache first
    cached_hash = _get_cached_hash(file_path)
    if cached_hash:
        file_hash = cached_hash
        logger.debug(f"Using cached hash for {file_path.name}")
    else:
        # Compute hash and cache it
        file_hash = _sha256(file_path)
        _cache_hash(file_path, file_hash)
        logger.debug(f"Computed and cached hash for {file_path.name}")

    loader = _build_loader(file_path)

    try:
        docs = loader.load()
    except Exception as exc:
        raise RuntimeError(f"Failed to load '{file_path.name}': {exc}") from exc

    if not docs:
        logger.warning("Loader returned 0 documents for: {}", file_path.name)
        return []

    enriched = [_enrich_metadata(doc, file_path, file_hash) for doc in docs]
    logger.info(
        "Loaded {} page(s) from '{}' ({} bytes)",
        len(enriched),
        file_path.name,
        file_path.stat().st_size,
    )
    return enriched


def load_directory(
    dir_path: Path,
    glob: str = "**/*",
    recursive: bool = True,
) -> Iterator[tuple[Path, list[Document]]]:
    """
    Lazily load every supported file under *dir_path*.

    Yields (file_path, documents) tuples so the caller can stream
    results into the ingestion pipeline without holding all docs in memory.
    """
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {dir_path}")

    supported_exts = set(_LOADER_MAP.keys())
    pattern = "**/*" if recursive else "*"

    candidates = [p for p in dir_path.glob(pattern) if p.is_file()]
    supported = [p for p in candidates if p.suffix.lower() in supported_exts]

    logger.info(
        "Found {} supported file(s) out of {} total under '{}'",
        len(supported),
        len(candidates),
        dir_path,
    )

    for file_path in supported:
        try:
            docs = load_file(file_path)
            yield file_path, docs
        except Exception as exc:
            logger.error("Skipping '{}': {}", file_path.name, exc)
            continue
