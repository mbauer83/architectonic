"""SSE event bus and /api/events streaming endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.infrastructure.backend.shutdown import shutdown_signal
from src.infrastructure.rest.routers._openapi import TAG_PLATFORM, media_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=[TAG_PLATFORM])


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

#: How long a stream waits for an event before emitting a heartbeat.
_HEARTBEAT_SECONDS = 15.0

async def _next_event(
    queue: asyncio.Queue[dict[str, Any]], stopping: asyncio.Event
) -> dict[str, Any] | None:
    """The next event, or ``None`` when the heartbeat is due or the process is stopping.

    Races the queue against the stop signal rather than waiting on the queue alone: a stream blocked
    in `queue.get()` would otherwise hold its connection open until the next heartbeat, and one
    heartbeat is longer than the whole connection-drain budget (`shutdown.DRAIN_SECONDS`).
    """
    getter: asyncio.Future[dict[str, Any]] = asyncio.ensure_future(queue.get())
    waiting: asyncio.Future[bool] = asyncio.ensure_future(stopping.wait())
    try:
        done, _pending = await asyncio.wait(
            {getter, waiting}, timeout=_HEARTBEAT_SECONDS, return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in (getter, waiting):
            if not task.done():
                task.cancel()
    return getter.result() if getter in done else None


async def _event_stream(queue: asyncio.Queue[dict[str, Any]]) -> AsyncGenerator[str, None]:
    """Stream events from the queue with heartbeat, ending when the process stops.

    Ending on the shutdown signal is not a courtesy: uvicorn will not run the lifespan teardown
    until open connections drain, so a stream that outlives the signal is what stops the process
    from stopping. See ``backend.shutdown`` for the contract this observes.
    """
    stopping = shutdown_signal.waiter()
    try:
        while not shutdown_signal.is_set():
            event = await _next_event(queue, stopping)
            if event is None:
                if shutdown_signal.is_set():
                    break
                # Heartbeat: the only thing that reveals a connection the peer has abandoned.
                yield "event: heartbeat\ndata: {}\n\n"
                continue
            event_type = event.get("type", "message")
            yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
        # Named, so a client can tell an orderly server shutdown from a dropped connection and
        # reconnect deliberately instead of treating it as an error.
        yield "event: shutdown\ndata: {}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        shutdown_signal.release(stopping)
        await event_bus.unsubscribe(queue)


@router.get("/api/events",
    response_class=StreamingResponse,
    responses=media_response("text/event-stream", "Server-sent events until the client leaves"))
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
