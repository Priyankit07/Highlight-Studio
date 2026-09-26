"""
In-memory Server-Sent Events (SSE) broker for real-time job streaming.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class EventBroker:
    def __init__(self) -> None:
        # job_id -> set of asyncio.Queue
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = set()
            self._subscribers[job_id].add(queue)
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            if job_id in self._subscribers:
                self._subscribers[job_id].discard(queue)
                if not self._subscribers[job_id]:
                    del self._subscribers[job_id]

    def publish_nowait(self, job_id: str, event_type: str, data: Any = None) -> None:
        """Publish event to all active subscribers of job_id synchronously (thread-safe)."""
        payload = {"event": event_type, "data": data or {}}
        if job_id in self._subscribers:
            for q in list(self._subscribers[job_id]):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                        q.put_nowait(payload)
                    except Exception:
                        pass
                except Exception:
                    pass

    async def event_generator(self, job_id: str) -> AsyncGenerator[str, None]:
        """Generate formatted SSE message strings with 15s keepalive ping."""
        q = await self.subscribe(job_id)
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    event_type = msg["event"]
                    data_json = json.dumps(msg["data"])
                    yield f"event: {event_type}\ndata: {data_json}\n\n"
                except asyncio.TimeoutError:
                    # 15s keepalive comment ping
                    yield ": ping\n\n"
        finally:
            await self.unsubscribe(job_id, q)


broker = EventBroker()
