"""SSE event bus and /api/events streaming endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


class EventBus:
    """Async-safe event bus for broadcasting SSE events to multiple subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def _coalesce_key(event: dict[str, Any]) -> tuple[str, str | None] | None:
        event_type = str(event.get("type", "message"))
        if event_type in {"artifact_write_completed", "sync_status_changed", "sync_repository_updated"}:
            repo = event.get("repo")
            return (event_type, str(repo) if isinstance(repo, str) else None)
        return None

    @staticmethod
    def _coalesce_queue(queue: asyncio.Queue[dict[str, Any]], key: tuple[str, str | None]) -> None:
        raw_queue = getattr(queue, "_queue", None)
        if not isinstance(raw_queue, deque):
            return
        filtered = deque(item for item in raw_queue if EventBus._coalesce_key(item) != key)
        if len(filtered) != len(raw_queue):
            raw_queue.clear()
            raw_queue.extend(filtered)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to the event bus. Returns a queue of events."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        """Unsubscribe from the event bus."""
        async with self._lock:
            self._subscribers.discard(q)

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers. Drops slow subscribers."""
        coalesce_key = self._coalesce_key(event)
        async with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    if coalesce_key is not None:
                        self._coalesce_queue(q, coalesce_key)
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)


event_bus = EventBus()  # module-level singleton


async def _event_stream(queue: asyncio.Queue[dict[str, Any]]) -> AsyncGenerator[str, None]:
    """Stream events from the queue with heartbeat."""
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_type = event.get("type", "message")
                data = json.dumps(event)
                yield f"event: {event_type}\ndata: {data}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to detect dead connections
                yield "event: heartbeat\ndata: {}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await event_bus.unsubscribe(queue)


@router.get("/api/events")
async def stream_events() -> StreamingResponse:
    """SSE endpoint for real-time event streaming."""
    queue = await event_bus.subscribe()
    return StreamingResponse(
        _event_stream(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
