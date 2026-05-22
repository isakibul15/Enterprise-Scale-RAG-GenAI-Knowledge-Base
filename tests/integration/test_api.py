"""
FastAPI endpoint integration tests.

Uses httpx.AsyncClient with the app in ASGI test mode — no real server
is started.  Heavy singletons (ChromaDB, embedding model, LLM) are patched
via FastAPI's dependency_overrides and unittest.mock.patch so the tests
are fast and hermetic.
"""

import io
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.api.dependencies import get_ingestion_pipeline
from app.ingestion.pipeline import IngestionResult


# ---------------------------------------------------------------------------
# Async test client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired to the FastAPI app (no server required)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mocked pipeline fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    pipeline.ingest_file.return_value = IngestionResult(
        total_files=1,
        successful_files=["/data/uploads/test.txt"],
        failed_files=[],
        total_child_chunks=5,
        total_parent_chunks=2,
        duration_seconds=0.42,
    )
    return pipeline


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        with (
            patch("app.api.routes.health.get_chroma_client") as mock_chroma,
            patch("app.api.routes.health.get_embedding_model"),
        ):
            mock_chroma.return_value.heartbeat.return_value = 1234567890
            response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("ok", "degraded")
        assert "chromadb" in body
        assert "embedding_model" in body

    @pytest.mark.asyncio
    async def test_health_degraded_when_chroma_fails(self, client):
        with (
            patch("app.api.routes.health.get_chroma_client") as mock_chroma,
            patch("app.api.routes.health.get_embedding_model"),
        ):
            mock_chroma.return_value.heartbeat.side_effect = Exception("DB error")
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["chromadb"] == "unavailable"

    @pytest.mark.asyncio
    async def test_health_response_has_request_id_header(self, client):
        with (
            patch("app.api.routes.health.get_chroma_client") as mock_chroma,
            patch("app.api.routes.health.get_embedding_model"),
        ):
            mock_chroma.return_value.heartbeat.return_value = 1
            response = await client.get("/health")

        assert "x-request-id" in response.headers


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    @pytest.mark.asyncio
    async def test_upload_txt_returns_201(self, client, mock_pipeline):
        app.dependency_overrides[get_ingestion_pipeline] = lambda: mock_pipeline

        file_content = b"This is a test document with enough content for ingestion."
        response = await client.post(
            "/upload",
            files={"file": ("test_doc.txt", io.BytesIO(file_content), "text/plain")},
        )

        app.dependency_overrides.clear()
        assert response.status_code == 201
        body = response.json()
        assert body["file_name"] == "test_doc.txt"
        assert body["total_child_chunks"] == 5
        assert body["total_parent_chunks"] == 2
        assert "ingested successfully" in body["message"]

    @pytest.mark.asyncio
    async def test_upload_rejects_unsupported_extension(self, client):
        response = await client.post(
            "/upload",
            files={"file": ("malware.exe", io.BytesIO(b"bad"), "application/octet-stream")},
        )
        assert response.status_code == 415
        assert ".exe" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_rejects_missing_filename(self, client):
        response = await client.post(
            "/upload",
            files={"file": ("", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_pdf_accepted(self, client, mock_pipeline):
        app.dependency_overrides[get_ingestion_pipeline] = lambda: mock_pipeline
        response = await client.post(
            "/upload",
            files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        app.dependency_overrides.clear()
        # 201 or 422 depending on whether pipeline errors, but never 415
        assert response.status_code != 415


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    @pytest.mark.asyncio
    async def test_query_returns_answer(self, client):
        mock_result = MagicMock()
        mock_result.answer = "The refund window is 30 days. [Source: policy.pdf]"
        mock_result.sources = []
        mock_result.session_id = "test-session"
        mock_result.retrieved_chunks = 3
        mock_result.latency_ms = 420.0

        with patch("app.api.routes.query.ask", return_value=mock_result):
            response = await client.post(
                "/query",
                json={"question": "What is the refund policy?", "session_id": "test-session"},
            )

        assert response.status_code == 200
        body = response.json()
        assert "answer" in body
        assert body["session_id"] == "test-session"
        assert isinstance(body["sources"], list)
        assert isinstance(body["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_query_rejects_short_question(self, client):
        response = await client.post(
            "/query",
            json={"question": "Hi"},   # min_length=3 but "Hi" is 2 chars
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_rejects_invalid_session_id(self, client):
        response = await client.post(
            "/query",
            json={"question": "Valid question here", "session_id": "bad/session/../id"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_propagates_llm_error(self, client):
        with patch("app.api.routes.query.ask", side_effect=RuntimeError("LLM timeout")):
            response = await client.post(
                "/query",
                json={"question": "Anything at all?", "session_id": "err-session"},
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /query/stream
# ---------------------------------------------------------------------------

class TestStreamEndpoint:
    @pytest.mark.asyncio
    async def test_stream_returns_sse_content_type(self, client):
        async def fake_stream(*args, **kwargs):
            for token in ["Hello", " world", "."]:
                yield token

        with patch("app.api.routes.query.stream_ask", side_effect=fake_stream):
            response = await client.post(
                "/query/stream",
                json={"question": "Stream this question please", "session_id": "s1"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_stream_body_contains_done_sentinel(self, client):
        async def fake_stream(*args, **kwargs):
            yield "token"

        with patch("app.api.routes.query.stream_ask", side_effect=fake_stream):
            response = await client.post(
                "/query/stream",
                json={"question": "Stream this question please", "session_id": "s2"},
            )

        assert "[DONE]" in response.text


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionEndpoints:
    @pytest.mark.asyncio
    async def test_delete_session_returns_200(self, client):
        with patch("app.api.routes.query.clear_session") as mock_clear:
            response = await client.delete("/query/session/my-session-id")
        assert response.status_code == 200
        mock_clear.assert_called_once_with("my-session-id")

    @pytest.mark.asyncio
    async def test_list_sessions_returns_dict(self, client):
        with patch("app.api.routes.query.list_sessions", return_value=["s1", "s2"]):
            response = await client.get("/query/sessions")
        assert response.status_code == 200
        assert response.json()["count"] == 2
