"""Asynchronous Streaming Discovery Queue for Event-Driven Producer-Consumer Pipeline."""

import asyncio
import logging
from typing import Any, Callable, Coroutine, List, Optional
from src.core.models import JobPosting

log = logging.getLogger(__name__)


class StreamingDiscoveryQueue:
    """Decouples job crawling from evaluation via an in-memory asynchronous producer-consumer stream."""

    def __init__(self, maxsize: int = 1000) -> None:
        self.queue: asyncio.Queue[JobPosting] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, job: JobPosting) -> None:
        """Push a newly discovered job onto the ingestion stream."""
        await self.queue.put(job)

    async def dequeue(self) -> JobPosting:
        """Pop the next discovered job for evaluation."""
        return await self.queue.get()

    def qsize(self) -> int:
        """Return number of pending items in queue."""
        return self.queue.qsize()

    async def process_stream(
        self,
        handler: Callable[[JobPosting], Coroutine[Any, Any, None]],
        max_jobs: Optional[int] = None,
        timeout: float = 2.0,
    ) -> int:
        """Consume and process stream items sequentially or concurrently until exhausted."""
        processed = 0
        while True:
            if max_jobs is not None and processed >= max_jobs:
                break
            try:
                job = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                await handler(job)
                self.queue.task_done()
                processed += 1
            except asyncio.TimeoutError:
                break
            except Exception as exc:
                log.warning("Stream handler error on job %s: %s", getattr(job, "id", "unknown"), exc)
                self.queue.task_done()

        return processed
