"""Asynchronous telemetry sink queue with batch SQLite WAL flushing."""

import asyncio
import json
import sqlite3
from typing import Dict, Any, Optional, List


class TelemetrySink:
    """Asynchronous batch flushing telemetry sink into SQLite."""

    def __init__(
        self,
        telemetry_path: str = "./data/telemetry.db",
        flush_interval: float = 0.5,
        batch_size: int = 50,
    ) -> None:
        self.telemetry_path = telemetry_path
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the background flush loop."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._flush_loop())

    async def log_span(self, span_data: Dict[str, Any]) -> None:
        """Enqueue span data for asynchronous batch writing."""
        if self._running:
            await self.queue.put(span_data)

    async def log_event(self, event: Dict[str, Any]) -> None:
        """Enqueue event data (alias for log_span)."""
        await self.log_span(event)

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Write a batch of span entries to the telemetry database."""
        if not batch:
            return

        rows = []
        for item in batch:
            span_id = item.get("span_id")
            event = item.get("event")
            tokens = item.get("tokens", 0)
            metadata = item.get("metadata")
            if isinstance(metadata, (dict, list)):
                metadata_str = json.dumps(metadata)
            elif metadata is not None:
                metadata_str = str(metadata)
            else:
                metadata_str = None

            rows.append({
                "span_id": span_id,
                "event": event,
                "tokens": tokens,
                "metadata": metadata_str,
            })

        with sqlite3.connect(self.telemetry_path, timeout=30.0) as conn:
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.executemany(
                """
                INSERT INTO audit_spans (span_id, event, tokens, metadata)
                VALUES (:span_id, :event, :tokens, :metadata)
                """,
                rows,
            )
            conn.commit()

    async def _flush_loop(self) -> None:
        """Continuous tight-drain flush loop while running or queue is not empty."""
        while self._running or not self.queue.empty():
            batch: List[Dict[str, Any]] = []
            try:
                while len(batch) < self.batch_size:
                    item = self.queue.get_nowait()
                    batch.append(item)
                    self.queue.task_done()
            except asyncio.QueueEmpty:
                pass

            if batch:
                self._write_batch(batch)

            # If still have items queued, drain tightly; otherwise wait flush_interval
            if not self.queue.empty():
                await asyncio.sleep(0)  # Yield control to event loop without waiting full interval
            elif self._running:
                await asyncio.sleep(self.flush_interval)

    async def flush_and_close(self) -> None:
        """Stop accepting new items, drain remaining queue, and wait for worker completion."""
        self._running = False
        if self._worker_task:
            await self._worker_task
            self._worker_task = None
