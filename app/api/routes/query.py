"""
Query routes.

POST /query          — one-shot answer, returns full QueryResponse JSON.
POST /query/stream   — same pipeline but answer is streamed token-by-token
                       as Server-Sent Events (text/event-stream).
DELETE /query/session/{session_id}
                     — wipe the chat history for a given session.
GET  /query/sessions — list active in-memory session IDs (debug / admin).
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.requests import ClearSessionRequest, QueryRequest
from app.models.responses import ErrorResponse, QueryResponse, SourceDocumentSchema
from app.retrieval.chain import RAGResponse, ask, clear_session, list_sessions, stream_ask

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /query  — synchronous (LLM blocks; run in thread so event loop is free)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question",
    description=(
        "Send a natural-language question. The pipeline retrieves relevant "
        "document chunks from ChromaDB, feeds them into the LLM with an "
        "anti-hallucination prompt, and returns the grounded answer with sources."
    ),
    responses={
        200: {"description": "Answer generated successfully"},
        400: {"model": ErrorResponse, "description": "Empty or invalid question"},
        500: {"model": ErrorResponse, "description": "LLM or retrieval error"},
    },
)
async def query(request: QueryRequest) -> QueryResponse:
    logger.info(
        "Query | session={} | top_k={} | parent={} | q='{}'",
        request.session_id,
        request.top_k,
        request.use_parent_retriever,
        request.question[:100],
    )

    try:
        # ask() is synchronous (LLM call blocks) — offload to thread pool
        result: RAGResponse = await asyncio.to_thread(
            ask,
            request.question,
            request.session_id,
        )
    except Exception as exc:
        logger.exception("Query failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return QueryResponse(
        answer=result.answer,
        sources=[
            SourceDocumentSchema(
                file_name=s.file_name,
                source=s.source,
                chunk_id=s.chunk_id,
                page=s.page,
                snippet=s.snippet,
            )
            for s in result.sources
        ],
        session_id=result.session_id,
        retrieved_chunks=result.retrieved_chunks,
        latency_ms=result.latency_ms,
    )


# ---------------------------------------------------------------------------
# POST /query/stream  — SSE token streaming
# ---------------------------------------------------------------------------

@router.post(
    "/stream",
    summary="Stream an answer via Server-Sent Events",
    description=(
        "Same as POST /query but the answer is streamed token-by-token. "
        "Connect with an EventSource client. Each SSE event carries a JSON "
        "payload: `{\"token\": \"...\"}`. A final `[DONE]` event signals completion."
    ),
    response_class=StreamingResponse,
)
async def stream_query(request: QueryRequest) -> StreamingResponse:
    logger.info(
        "Stream query | session={} | q='{}'",
        request.session_id,
        request.question[:100],
    )

    async def event_generator():
        try:
            async for token in stream_ask(request.question, request.session_id):
                payload = json.dumps({"token": token}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.exception("Stream error for session {}: {}", request.session_id, exc)
            error_payload = json.dumps({"error": str(exc)})
            yield f"data: {error_payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx: disable proxy buffering so tokens reach the client immediately
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# DELETE /query/session/{session_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/session/{session_id}",
    summary="Clear chat history",
    description="Wipe the conversation history for a given session_id.",
)
async def delete_session(session_id: str) -> dict:
    clear_session(session_id)
    return {"message": f"Session '{session_id}' cleared."}


# ---------------------------------------------------------------------------
# GET /query/sessions  — debug / admin only
# ---------------------------------------------------------------------------

@router.get(
    "/sessions",
    summary="List active sessions (admin)",
    description="Returns all in-memory session IDs. Disable in production via middleware.",
)
async def get_sessions() -> dict:
    sessions = list_sessions()
    return {"active_sessions": sessions, "count": len(sessions)}
