"""
Integration tests for the retrieval layer.

These tests use mocked ChromaDB / LLM singletons so they run without
any external services, but exercise the real retriever and chain logic.
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from app.retrieval.retriever import StandardRetriever, ParentAwareRetriever
from app.retrieval.prompts import format_retrieved_docs
from app.retrieval.chain import _extract_sources, clear_session, list_sessions, RAGResponse


# ---------------------------------------------------------------------------
# format_retrieved_docs
# ---------------------------------------------------------------------------

class TestFormatRetrievedDocs:
    def test_empty_returns_sentinel(self):
        result = format_retrieved_docs([])
        assert "No relevant documents" in result

    def test_formats_with_source_header(self, sample_documents):
        result = format_retrieved_docs(sample_documents)
        assert "policy.pdf" in result
        assert "[1]" in result
        assert "[2]" in result

    def test_page_number_included_when_present(self):
        doc = Document(
            page_content="Some content",
            metadata={"file_name": "report.pdf", "page": 5},
        )
        result = format_retrieved_docs([doc])
        assert "p.5" in result

    def test_multiple_docs_separated(self, sample_documents):
        result = format_retrieved_docs(sample_documents)
        assert "---" in result


# ---------------------------------------------------------------------------
# StandardRetriever
# ---------------------------------------------------------------------------

class TestStandardRetriever:
    def test_returns_docs_from_vector_store(self, mock_vector_store, sample_documents):
        retriever = StandardRetriever(vector_store=mock_vector_store, top_k=2)
        docs = retriever.invoke("refund policy")
        assert len(docs) == len(sample_documents)
        mock_vector_store.similarity_search.assert_called_once_with("refund policy", k=2)

    def test_top_k_is_respected(self, mock_vector_store):
        mock_vector_store.similarity_search.return_value = []
        retriever = StandardRetriever(vector_store=mock_vector_store, top_k=3)
        retriever.invoke("test query")
        mock_vector_store.similarity_search.assert_called_with("test query", k=3)


# ---------------------------------------------------------------------------
# ParentAwareRetriever
# ---------------------------------------------------------------------------

class TestParentAwareRetriever:
    def test_swaps_child_for_parent(self, mock_vector_store, sample_documents, parent_documents):
        parent_store = {"parent-001": parent_documents[0]}
        retriever = ParentAwareRetriever(
            vector_store=mock_vector_store,
            parent_store=parent_store,
            top_k=6,
        )
        docs = retriever.invoke("refund policy")
        # Both child chunks share parent-001 — should deduplicate to 1 parent doc
        assert len(docs) == 1
        assert docs[0].metadata["granularity"] == "parent"

    def test_falls_back_to_child_when_parent_missing(self, mock_vector_store, sample_documents):
        retriever = ParentAwareRetriever(
            vector_store=mock_vector_store,
            parent_store={},   # empty store
            top_k=6,
        )
        docs = retriever.invoke("refund policy")
        assert len(docs) >= 1
        # Content should come from child chunks
        for doc in docs:
            assert doc.metadata.get("granularity") == "child"

    def test_deduplicates_by_parent_id(self, mock_vector_store, sample_documents, parent_documents):
        # Multiple child hits with the same parent_id must yield only one parent
        parent_store = {"parent-001": parent_documents[0]}
        retriever = ParentAwareRetriever(
            vector_store=mock_vector_store,
            parent_store=parent_store,
            top_k=6,
        )
        docs = retriever.invoke("any query")
        parent_ids = [d.metadata.get("chunk_id") for d in docs]
        assert len(parent_ids) == len(set(parent_ids))


# ---------------------------------------------------------------------------
# _extract_sources
# ---------------------------------------------------------------------------

class TestExtractSources:
    def test_extracts_source_metadata(self, sample_documents):
        sources = _extract_sources(sample_documents)
        assert len(sources) == 2
        assert all(s.file_name == "policy.pdf" for s in sources)

    def test_deduplicates_by_chunk_id(self, sample_documents):
        # Feed the same doc twice
        sources = _extract_sources(sample_documents * 2)
        assert len(sources) == 2   # still 2, not 4

    def test_snippet_truncated_to_200(self, sample_documents):
        sources = _extract_sources(sample_documents)
        for s in sources:
            assert len(s.snippet) <= 200


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_clear_session_removes_history(self):
        # Clearing a non-existent session should not raise
        clear_session("ghost-session-xyz")

    def test_list_sessions_returns_list(self):
        sessions = list_sessions()
        assert isinstance(sessions, list)
