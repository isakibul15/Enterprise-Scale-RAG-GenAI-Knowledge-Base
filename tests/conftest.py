"""
Shared pytest fixtures.

Heavy singletons (embedding model, ChromaDB client, LLM) are patched so unit
and integration tests run fast without network or GPU requirements.
"""

import pytest
from langchain_core.documents import Document
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fake Documents
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_documents():
    return [
        Document(
            page_content="The enterprise refund policy allows returns within 30 days of purchase.",
            metadata={
                "source": "/data/policy.pdf",
                "file_name": "policy.pdf",
                "file_type": "pdf",
                "file_hash": "abc123",
                "chunk_id": "chunk-001",
                "parent_id": "parent-001",
                "chunk_index": 0,
                "granularity": "child",
                "loaded_at": "2025-01-01T00:00:00Z",
            },
        ),
        Document(
            page_content="Refunds are processed within 5-7 business days after approval.",
            metadata={
                "source": "/data/policy.pdf",
                "file_name": "policy.pdf",
                "file_type": "pdf",
                "file_hash": "abc123",
                "chunk_id": "chunk-002",
                "parent_id": "parent-001",
                "chunk_index": 1,
                "granularity": "child",
                "loaded_at": "2025-01-01T00:00:00Z",
            },
        ),
    ]


@pytest.fixture
def parent_documents():
    return [
        Document(
            page_content=(
                "The enterprise refund policy allows returns within 30 days of purchase. "
                "Refunds are processed within 5-7 business days after approval. "
                "Items must be in original condition and packaging."
            ),
            metadata={
                "source": "/data/policy.pdf",
                "file_name": "policy.pdf",
                "chunk_id": "parent-001",
                "granularity": "parent",
                "chunk_index": 0,
            },
        )
    ]


# ---------------------------------------------------------------------------
# Mocked vector store
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_vector_store(sample_documents):
    store = MagicMock()
    store.similarity_search.return_value = sample_documents
    store.similarity_search_with_score.return_value = [
        (doc, 0.92) for doc in sample_documents
    ]
    return store


# ---------------------------------------------------------------------------
# Mocked LLM
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(
        content="Based on the provided context, the refund policy allows 30 days. [Source: policy.pdf]"
    )
    llm.stream.return_value = iter([
        MagicMock(content="Based "),
        MagicMock(content="on the context, "),
        MagicMock(content="30 days."),
    ])
    return llm


# ---------------------------------------------------------------------------
# Patch heavy singletons for all tests that need them
# ---------------------------------------------------------------------------

@pytest.fixture
def patch_singletons(mock_vector_store, mock_llm):
    """Patch embedding model, ChromaDB client, and LLM to avoid I/O in tests."""
    with (
        patch("app.retrieval.vector_store.get_chroma_client") as mock_chroma,
        patch("app.retrieval.vector_store.get_langchain_vector_store", return_value=mock_vector_store),
        patch("app.ingestion.embedder.get_embedding_model") as mock_embed,
        patch("app.retrieval.llm.get_llm", return_value=mock_llm),
    ):
        mock_chroma.return_value = MagicMock()
        mock_embed.return_value = MagicMock(
            embed_documents=lambda texts: [[0.1] * 1024] * len(texts),
            embed_query=lambda text: [0.1] * 1024,
        )
        yield
