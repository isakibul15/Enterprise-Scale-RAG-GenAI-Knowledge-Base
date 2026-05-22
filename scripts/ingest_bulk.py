#!/usr/bin/env python3
"""
CLI bulk ingestion script.

Usage:
    # Ingest a single file
    python scripts/ingest_bulk.py --path data/raw/report.pdf

    # Ingest an entire directory (recursive)
    python scripts/ingest_bulk.py --path data/raw/ --recursive

    # Override chunk settings at runtime
    python scripts/ingest_bulk.py --path data/raw/ --chunk-size 256 --chunk-overlap 32

    # Target a specific Qdrant collection
    python scripts/ingest_bulk.py --path data/raw/ --collection my_collection

    # Dry-run: only load and split, skip Qdrant upsert
    python scripts/ingest_bulk.py --path data/raw/ --dry-run
"""

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import configure_logging
from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enterprise RAG — bulk document ingestion CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="File or directory to ingest",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Recursively scan sub-directories (directory mode only)",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Disable recursive directory scanning",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Qdrant collection name (defaults to QDRANT_COLLECTION_NAME env var)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Child chunk character size (overrides CHUNK_SIZE env var)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Child chunk overlap (overrides CHUNK_OVERLAP env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Number of chunks per Qdrant upsert batch",
    )
    parser.add_argument(
        "--no-re-ingest",
        dest="re_ingest",
        action="store_false",
        default=True,
        help="Skip deletion of existing vectors for the same source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Load and chunk documents without upserting into Qdrant",
    )
    return parser.parse_args()


def dry_run(path: Path, recursive: bool, chunk_size, chunk_overlap) -> None:
    """Load + split only — useful for validating documents before ingestion."""
    from app.ingestion.loader import load_file, load_directory
    from app.ingestion.splitter import DocumentSplitter

    splitter = DocumentSplitter(
        child_chunk_size=chunk_size,
        child_chunk_overlap=chunk_overlap,
    )

    if path.is_file():
        docs = load_file(path)
        result = splitter.split(docs)
        logger.info(
            "[DRY RUN] '{}' → {} child chunks, {} parent chunks",
            path.name,
            len(result.child_chunks),
            len(result.parent_chunks),
        )
    else:
        total_children = total_parents = 0
        for file_path, docs in load_directory(path, recursive=recursive):
            result = splitter.split(docs)
            total_children += len(result.child_chunks)
            total_parents += len(result.parent_chunks)
            logger.info(
                "[DRY RUN] '{}' → {} child, {} parent",
                file_path.name,
                len(result.child_chunks),
                len(result.parent_chunks),
            )
        logger.info(
            "[DRY RUN] Total: {} child chunks, {} parent chunks",
            total_children,
            total_parents,
        )


def main() -> int:
    configure_logging()
    args = parse_args()

    if not args.path.exists():
        logger.error("Path does not exist: {}", args.path)
        return 1

    if args.dry_run:
        logger.info("Dry-run mode — no data will be written to Qdrant")
        dry_run(args.path, args.recursive, args.chunk_size, args.chunk_overlap)
        return 0

    from app.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        collection_name=args.collection,
        re_ingest=args.re_ingest,
        child_chunk_size=args.chunk_size,
        child_chunk_overlap=args.chunk_overlap,
        batch_size=args.batch_size,
    )

    if args.path.is_file():
        result = pipeline.ingest_file(args.path)
    else:
        result = pipeline.ingest_directory(args.path, recursive=args.recursive)

    return 0 if not result.failed_files else 1


if __name__ == "__main__":
    sys.exit(main())
