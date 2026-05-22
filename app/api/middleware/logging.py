"""
Request logging + timing middleware.

Assigns a short request-ID to every incoming request and logs:
  - method, path, query string on arrival
  - status code + latency on completion

The request-ID is echoed back in X-Request-ID response header so callers
can correlate client-side and server-side logs.
"""

import time
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
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
