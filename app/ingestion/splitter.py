"""
Text chunking strategies.

Produces two granularities of chunks:
  - child chunks  → small, embedded and stored in ChromaDB (used for retrieval)
  - parent chunks → large, stored in a docstore (used for ParentDocumentRetriever in M3)

A stable `chunk_id` (UUID5 over source + content) enables idempotent upserts.
"""

import uuid
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from app.core.config import settings

# Sentinel namespace for stable UUID generation
_UUID_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _stable_id(source: str, content: str) -> str:
    """Deterministic UUID5 from (source, first-200-chars) — enables dedup upserts."""
    fingerprint = f"{source}::{content[:200]}"
    return str(uuid.uuid5(_UUID_NS, fingerprint))


def _tag_chunks(
    chunks: list[Document],
    granularity: str,
    parent_id: str | None = None,
) -> list[Document]:
    """Add chunk_id, granularity, and optional parent_id to metadata in place."""
    for i, chunk in enumerate(chunks):
        source = chunk.metadata.get("source", "unknown")
        chunk.metadata["chunk_id"] = _stable_id(source, chunk.page_content)
        chunk.metadata["chunk_index"] = i
        chunk.metadata["granularity"] = granularity
        if parent_id is not None:
            chunk.metadata["parent_id"] = parent_id
    return chunks


@dataclass
class SplitResult:
    child_chunks: list[Document]
    parent_chunks: list[Document]


class DocumentSplitter:
    """
    Splits raw documents into child and parent chunks.

    Child chunks are small (default 512 tokens) — optimised for dense retrieval.
    Parent chunks are large (default 2048 tokens) — used by ParentDocumentRetriever
    to return broader context after a child hit is found.
    """

    def __init__(
        self,
        child_chunk_size: int | None = None,
        child_chunk_overlap: int | None = None,
        parent_chunk_size: int | None = None,
    ) -> None:
        child_size = child_chunk_size or settings.chunk_size
        child_overlap = child_chunk_overlap or settings.chunk_overlap
        parent_size = parent_chunk_size or settings.parent_chunk_size

        self._child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_size,
            chunk_overlap=child_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            add_start_index=True,  # stores char offset in metadata
        )
        self._parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_size,
            chunk_overlap=child_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            add_start_index=True,
        )

    def split(self, documents: list[Document]) -> SplitResult:
        """
        Split *documents* into (child_chunks, parent_chunks).

        Both share provenance metadata from the source document.
        Child chunks carry a `parent_id` linking back to their parent chunk.
        """
        if not documents:
            return SplitResult(child_chunks=[], parent_chunks=[])

        all_children: list[Document] = []
        all_parents: list[Document] = []

        for doc in documents:
            # --- parent pass ---
            parents = self._parent_splitter.split_documents([doc])
            _tag_chunks(parents, granularity="parent")

            # --- child pass (split each parent, not the full doc) ---
            for parent in parents:
                children = self._child_splitter.split_documents([parent])
                _tag_chunks(
                    children,
                    granularity="child",
                    parent_id=parent.metadata["chunk_id"],
                )
                all_children.extend(children)

            all_parents.extend(parents)

        logger.info(
            "Split {} document(s) → {} parent chunk(s), {} child chunk(s)",
            len(documents),
            len(all_parents),
            len(all_children),
        )
        return SplitResult(child_chunks=all_children, parent_chunks=all_parents)
