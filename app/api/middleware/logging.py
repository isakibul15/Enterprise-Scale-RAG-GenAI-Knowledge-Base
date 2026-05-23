"""
Request logging + timing middleware.

Assigns a short request-ID to every incoming request and logs:
  - method, path, query string on arrival
  - status code + latency on completion

The request-ID is echoed back in X-Request-ID response header so callers
can correlate client-side and server-side logs.

Features:
  - Unique request ID generation for tracking
  - Request/response timing in milliseconds
  - Context-aware logging with request IDs
  - Response headers for client-side correlation
"""

import time
import uuid
from typing import Callable, Any

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging and timing."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """
        Process incoming request with logging and timing.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in the chain

        Returns:
            HTTP response with timing headers and request ID

        Raises:
            Propagates any unhandled exceptions from downstream handlers
        """
        request_id = uuid.uuid4().hex[:10]
        qs = f"?{request.url.query}" if request.url.query else ""

        with logger.contextualize(request_id=request_id):
            logger.info("→ {} {}{}", request.method, request.url.path, qs)
            t0 = time.perf_counter()

            try:
                response: Response = await call_next(request)
            except Exception as exc:
                logger.exception("Unhandled exception during request: {}", exc)
                raise

            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "← {} {}{} | {} | {:.1f}ms",
                request.method,
                request.url.path,
                qs,
                response.status_code,
                latency_ms,
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.1f}"
        return response
