"""Unit tests for DocumentSplitter — no network, no Qdrant."""

import pytest
from langchain_core.documents import Document

from app.ingestion.splitter import DocumentSplitter, _stable_id


@pytest.fixture
def sample_docs():
    return [
        Document(
            page_content="A" * 1000 + " sentence end. " + "B" * 1000,
            metadata={"source": "/tmp/test.txt", "file_name": "test.txt"},
        )
    ]


def test_stable_id_is_deterministic():
    id1 = _stable_id("source.txt", "hello world")
    id2 = _stable_id("source.txt", "hello world")
    assert id1 == id2


def test_stable_id_differs_by_source():
    id1 = _stable_id("a.txt", "hello world")
    id2 = _stable_id("b.txt", "hello world")
    assert id1 != id2


def test_split_produces_chunks(sample_docs):
    splitter = DocumentSplitter(child_chunk_size=256, child_chunk_overlap=32)
    result = splitter.split(sample_docs)
    assert len(result.child_chunks) > 1
    assert len(result.parent_chunks) >= 1


def test_child_chunks_carry_parent_id(sample_docs):
    splitter = DocumentSplitter(child_chunk_size=256, child_chunk_overlap=32)
    result = splitter.split(sample_docs)
    parent_ids = {p.metadata["chunk_id"] for p in result.parent_chunks}
    for child in result.child_chunks:
        assert child.metadata["parent_id"] in parent_ids


def test_chunk_ids_are_unique(sample_docs):
    splitter = DocumentSplitter(child_chunk_size=256, child_chunk_overlap=32)
    result = splitter.split(sample_docs)
    ids = [c.metadata["chunk_id"] for c in result.child_chunks]
    assert len(ids) == len(set(ids)), "chunk_ids must be unique"


def test_empty_input_returns_empty():
    splitter = DocumentSplitter()
    result = splitter.split([])
    assert result.child_chunks == []
    assert result.parent_chunks == []


def test_metadata_preserved(sample_docs):
    splitter = DocumentSplitter(child_chunk_size=256, child_chunk_overlap=32)
    result = splitter.split(sample_docs)
    for chunk in result.child_chunks:
        assert "source" in chunk.metadata
        assert chunk.metadata["granularity"] == "child"
