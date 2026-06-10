"""
Request deduplication middleware.

Prevents duplicate requests in-flight by caching pending promises.
Useful for slow queries where users might click "Ask" multiple times.
Caches based on session_id + query hash.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Any, Callable, Dict
from fastapi import Request
from functools import wraps
from loguru import logger


class RequestDeduplicator:
    """In-flight request deduplication using promise caching."""

    def __init__(self, ttl_seconds: int = 60):
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl_seconds

    def get_request_hash(self, session_id: str, query: str) -> str:
        """Generate hash for (session, query) pair."""
        combined = f"{session_id}:{query}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def is_duplicate(self, request_hash: str) -> bool:
        """Check if request is already in-flight."""
        if request_hash not in self.cache:
            return False

        _, timestamp = self.cache[request_hash]
        if datetime.now() - datetime.fromtimestamp(timestamp) > timedelta(seconds=self.ttl):
            del self.cache[request_hash]
            return False

        return True

    def add(self, request_hash: str, result: Any) -> None:
        """Cache result of request."""
        self.cache[request_hash] = (result, datetime.now().timestamp())

    def get(self, request_hash: str) -> Any | None:
        """Retrieve cached result."""
        if request_hash in self.cache:
            result, timestamp = self.cache[request_hash]
            if datetime.now() - datetime.fromtimestamp(timestamp) > timedelta(seconds=self.ttl):
                del self.cache[request_hash]
                return None
            return result
        return None

    def clear_session(self, session_id: str) -> None:
        """Clear all cache entries for a session (after session ends)."""
        prefix = f"{session_id}:"
        to_delete = [k for k in self.cache.keys() if k.startswith(prefix)]
        for k in to_delete:
            del self.cache[k]
        if to_delete:
            logger.debug(f"Cleared {len(to_delete)} cached requests for session {session_id}")


# Global deduplicator instance
_DEDUPLICATOR = RequestDeduplicator(ttl_seconds=60)


def deduplicate_request(func: Callable) -> Callable:
    """Decorator to deduplicate requests based on session_id + query."""

    @wraps(func)
    async def wrapper(question: str, session_id: str, *args, **kwargs):
        request_hash = _DEDUPLICATOR.get_request_hash(session_id, question)

        # Check if request is already in-flight
        if _DEDUPLICATOR.is_duplicate(request_hash):
            logger.debug(f"Duplicate request detected: {request_hash}")
            cached = _DEDUPLICATOR.get(request_hash)
            if cached is not None:
                return cached

        try:
            result = await func(question, session_id, *args, **kwargs)
            _DEDUPLICATOR.add(request_hash, result)
            return result
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    return wrapper


def get_deduplicator() -> RequestDeduplicator:
    """Get global deduplicator instance."""
    return _DEDUPLICATOR
