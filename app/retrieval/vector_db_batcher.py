"""
Vector database query batching utility.

Batches multiple retrieve requests into single DB queries.
Useful when processing multiple documents or concurrent requests.
Reduces ChromaDB round-trips and improves throughput.
"""

import asyncio
from typing import Optional
from datetime import datetime
from dataclasses import dataclass
from loguru import logger


@dataclass
class BatchItem:
    """Single item in a batch."""
    query: str
    k: int = 5
    session_id: Optional[str] = None
    future: asyncio.Future = None


class VectorDBBatcher:
    """
    Batches retrieve requests to ChromaDB.
    Accumulates requests for up to `batch_timeout_ms` then executes as single query.
    """

    def __init__(self, batch_timeout_ms: int = 50, max_batch_size: int = 10):
        self.batch_timeout_ms = batch_timeout_ms
        self.max_batch_size = max_batch_size
        self.pending_batch: list[BatchItem] = []
        self.batch_lock = asyncio.Lock()
        self.batch_event = asyncio.Event()
        self._batch_task = None

    async def add_to_batch(self, query: str, k: int = 5, session_id: Optional[str] = None):
        """
        Add a query to the batch.
        Returns a future that will be resolved when batch is executed.
        """
        future = asyncio.Future()
        item = BatchItem(query=query, k=k, session_id=session_id, future=future)

        async with self.batch_lock:
            self.pending_batch.append(item)
            logger.debug(f"Added to batch. Size: {len(self.pending_batch)}/{self.max_batch_size}")

            # Execute batch if full
            if len(self.pending_batch) >= self.max_batch_size:
                await self._execute_batch()
            # Or schedule for timeout
            elif len(self.pending_batch) == 1:
                asyncio.create_task(self._schedule_batch_timeout())

        return future

    async def _schedule_batch_timeout(self):
        """Schedule batch execution after timeout."""
        await asyncio.sleep(self.batch_timeout_ms / 1000.0)
        async with self.batch_lock:
            if self.pending_batch:
                await self._execute_batch()

    async def _execute_batch(self):
        """Execute the accumulated batch."""
        batch = self.pending_batch.copy()
        self.pending_batch.clear()

        if not batch:
            return

        logger.info(f"Executing batched retrieve: {len(batch)} queries")

        # In a real implementation, you'd batch these calls to ChromaDB
        # For now, we'll execute them concurrently
        tasks = [
            self._execute_single_retrieve(item)
            for item in batch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item, result in zip(batch, results):
            if isinstance(result, Exception):
                item.future.set_exception(result)
            else:
                item.future.set_result(result)

    async def _execute_single_retrieve(self, item: BatchItem):
        """Execute single retrieve (placeholder for actual DB call)."""
        # This would be replaced with actual ChromaDB retriever call
        # For now, returning placeholder
        await asyncio.sleep(0.01)  # Simulate DB latency
        return {
            "documents": [],
            "metadatas": [],
            "distances": [],
            "query": item.query,
        }

    def stats(self) -> dict:
        """Get batcher statistics."""
        return {
            "pending_items": len(self.pending_batch),
            "max_batch_size": self.max_batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
        }


# Global batcher instance
_VECTOR_DB_BATCHER = VectorDBBatcher(batch_timeout_ms=50, max_batch_size=10)


def get_vector_db_batcher() -> VectorDBBatcher:
    """Get the global vector DB batcher."""
    return _VECTOR_DB_BATCHER
