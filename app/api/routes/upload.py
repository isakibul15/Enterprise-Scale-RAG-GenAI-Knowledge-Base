"""
POST /upload — ingest a document into the knowledge base.

Flow:
  1. Validate file extension and size.
  2. Persist the upload to data/uploads/ with aiofiles (non-blocking I/O).
  3. Run IngestionPipeline.ingest_file() in a thread pool so CPU-bound
     embedding work does not block the event loop.
  4. Return chunk counts and timing.
"""

import asyncio
import mimetypes
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from loguru import logger

from app.api.dependencies import get_ingestion_pipeline
from app.core.config import settings
from app.ingestion.pipeline import IngestionPipeline
from app.models.responses import UploadResponse

router = APIRouter()

# Extensions the pipeline can actually handle (mirrors loader.py _LOADER_MAP)
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".html", ".htm", ".csv"}
)


async def _save_upload(file: UploadFile, dest: Path) -> int:
    """
    Stream *file* to *dest* in 64 KB chunks.

    Returns the total number of bytes written.
    Raises HTTPException(413) if the file exceeds settings.max_upload_bytes.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    async with aiofiles.open(dest, "wb") as out:
        while chunk := await file.read(65_536):
            total += len(chunk)
            if total > settings.max_upload_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"File exceeds the {settings.max_upload_size_mb} MB limit. "
                        f"Received at least {total // (1024 * 1024)} MB."
                    ),
                )
            await out.write(chunk)

    return total


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document",
    description=(
        "Upload a PDF, DOCX, TXT, Markdown, HTML, or CSV file. "
        "The file is chunked, embedded, and stored in ChromaDB immediately."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="Document to ingest"),
    collection: str = Query(
        default=None,
        description="Target ChromaDB collection (defaults to COLLECTION_NAME env var).",
    ),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> UploadResponse:
    # --- Validate file name / extension ---
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file has no filename.",
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{suffix}' is not supported. "
                f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            ),
        )

    logger.info("Upload received: '{}'", file.filename)

    # --- Persist upload ---
    dest = settings.upload_dir / file.filename
    bytes_written = await _save_upload(file, dest)
    logger.info("Saved '{}' ({} bytes) → '{}'", file.filename, bytes_written, dest)

    # --- Ingest in thread pool (CPU-bound: tokenisation + embedding + ChromaDB) ---
    try:
        result = await asyncio.to_thread(
            pipeline.ingest_file,
            dest,
        )
    except Exception as exc:
        logger.exception("Ingestion failed for '{}': {}", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )

    if result.failed_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File was saved but ingestion produced errors: {result.failed_files}",
        )

    return UploadResponse(
        message=f"'{file.filename}' ingested successfully.",
        file_name=file.filename,
        total_child_chunks=result.total_child_chunks,
        total_parent_chunks=result.total_parent_chunks,
        duration_seconds=round(result.duration_seconds, 2),
        collection=collection or settings.collection_name,
    )
