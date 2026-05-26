"""
Performance monitoring middleware.

Tracks and aggregates:
  - Query cache hit/miss ratios
  - Average response latencies per endpoint
  - Embedding pipeline performance
  - Database operation latencies

Metrics are logged periodically and available via a /metrics endpoint.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Any
from collections import defaultdict

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


@dataclass
class MetricsCollector:
    """Aggregates performance metrics across requests."""
    
    cache_hits: int = 0
    cache_misses: int = 0
    endpoint_latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    total_requests: int = 0
    
    def record_cache_hit(self):
        self.cache_hits += 1
    
    def record_cache_miss(self):
        self.cache_misses += 1
    
    def record_latency(self, endpoint: str, latency_ms: float):
        self.endpoint_latencies[endpoint].append(latency_ms)
    
    def get_cache_hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total * 100
    
    def get_avg_latency(self, endpoint: str) -> float:
        latencies = self.endpoint_latencies.get(endpoint, [])
        if not latencies:
            return 0.0
        return sum(latencies) / len(latencies)
    
    def get_summary(self) -> dict:
        """Return a summary of collected metrics."""
        return {
            "total_requests": self.total_requests,
            "cache_hit_ratio_percent": round(self.get_cache_hit_ratio(), 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "endpoint_stats": {
                endpoint: {
                    "avg_latency_ms": round(self.get_avg_latency(endpoint), 2),
                    "request_count": len(latencies),
                }
                for endpoint, latencies in self.endpoint_latencies.items()
            },
        }
    
    def reset(self):
        """Reset all metrics."""
        self.cache_hits = 0
        self.cache_misses = 0
        self.endpoint_latencies.clear()
        self.total_requests = 0


# Global metrics collector
_metrics = MetricsCollector()


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking performance metrics across the application."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """
        Process incoming request with performance monitoring.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in the chain

        Returns:
            HTTP response with performance metrics in headers
        """
        # Check if this is a metrics endpoint request
        if request.url.path == "/metrics":
            return JSONResponse(_metrics.get_summary())
        
        endpoint = f"{request.method} {request.url.path}"
        t0 = time.perf_counter()
        
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logger.exception("Exception during performance monitoring: {}", exc)
            raise
        
        latency_ms = (time.perf_counter() - t0) * 1000
        
        # Record metrics
        _metrics.total_requests += 1
        _metrics.record_latency(endpoint, latency_ms)
        
        # Check response headers for cache status from downstream handlers
        if "X-Cache-Hit" in response.headers:
            if response.headers["X-Cache-Hit"].lower() == "true":
                _metrics.record_cache_hit()
            else:
                _metrics.record_cache_miss()
        
        # Add metrics to response headers
        response.headers["X-Cache-Hit-Ratio"] = f"{_metrics.get_cache_hit_ratio():.1f}%"
        
        # Log metrics periodically
        if _metrics.total_requests % 100 == 0:
            logger.info("Performance metrics | {}", _metrics.get_summary())
        
        return response


def get_metrics() -> dict:
    """Get current performance metrics."""
    return _metrics.get_summary()


def reset_metrics() -> None:
    """Reset all performance metrics."""
    _metrics.reset()
    logger.info("Performance metrics reset")
