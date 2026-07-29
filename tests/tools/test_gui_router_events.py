"""Tests for the EventBus class in events.py.

Covers subscribe/unsubscribe, publish (delivery + slow-subscriber drop),
coalesce key classification, coalesce queue, and multi-subscriber delivery.
"""

from __future__ import annotations

import asyncio

from src.infrastructure.gui.routers.events import EventBus

# ── subscribe / unsubscribe ───────────────────────────────────────────────────


class TestSubscribeUnsubscribe:
    def test_subscribe_adds_to_subscribers(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            assert q in bus._subscribers
            await bus.unsubscribe(q)

        asyncio.run(_run())

    def test_unsubscribe_removes_from_subscribers(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            await bus.unsubscribe(q)
            assert q not in bus._subscribers

        asyncio.run(_run())

    def test_unsubscribe_unknown_queue_is_safe(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = asyncio.Queue()
            await bus.unsubscribe(q)  # discard is a no-op

        asyncio.run(_run())


# ── publish ───────────────────────────────────────────────────────────────────


class TestPublish:
    def test_delivers_event_to_subscriber(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            event = {"type": "test", "x": 1}
            await bus.publish(event)
            received = q.get_nowait()
            assert received == event
            await bus.unsubscribe(q)

        asyncio.run(_run())

    def test_delivers_to_multiple_subscribers(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q1 = await bus.subscribe()
            q2 = await bus.subscribe()
            event = {"type": "test", "msg": "hi"}
            await bus.publish(event)
            assert q1.get_nowait() == event
            assert q2.get_nowait() == event
            await bus.unsubscribe(q1)
            await bus.unsubscribe(q2)

        asyncio.run(_run())

    def test_drops_full_subscriber(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            for i in range(64):  # maxsize=64
                q.put_nowait({"type": "filler", "i": i})
            await bus.publish({"type": "overflow"})
            assert q not in bus._subscribers

        asyncio.run(_run())


# ── _coalesce_key ─────────────────────────────────────────────────────────────


class TestCoalesceKey:
    def test_artifact_write_completed(self) -> None:
        key = EventBus._coalesce_key({"type": "artifact_write_completed", "repo": "/p"})
        assert key == ("artifact_write_completed", "/p")

    def test_sync_status_changed(self) -> None:
        key = EventBus._coalesce_key({"type": "sync_status_changed", "repo": "/p"})
        assert key == ("sync_status_changed", "/p")

    def test_sync_repository_updated(self) -> None:
        key = EventBus._coalesce_key({"type": "sync_repository_updated", "repo": "/p"})
        assert key == ("sync_repository_updated", "/p")

    def test_unknown_type_returns_none(self) -> None:
        key = EventBus._coalesce_key({"type": "other_event"})
        assert key is None

    def test_missing_type_defaults_to_message_which_is_not_coalesceable(self) -> None:
        key = EventBus._coalesce_key({})
        assert key is None

    def test_repo_none_when_missing(self) -> None:
        key = EventBus._coalesce_key({"type": "artifact_write_completed"})
        assert key == ("artifact_write_completed", None)

    def test_repo_none_when_non_string(self) -> None:
        key = EventBus._coalesce_key({"type": "artifact_write_completed", "repo": 42})
        assert key == ("artifact_write_completed", None)


# ── _coalesce_queue ───────────────────────────────────────────────────────────


class TestCoalesceQueue:
    def test_removes_matching_events(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            key = ("artifact_write_completed", "/r")
            q.put_nowait({"type": "artifact_write_completed", "repo": "/r"})
            q.put_nowait({"type": "artifact_write_completed", "repo": "/r"})
            EventBus._coalesce_queue(q, key)
            assert q.empty()
            await bus.unsubscribe(q)

        asyncio.run(_run())

    def test_keeps_non_matching_events(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            key = ("artifact_write_completed", "/r")
            q.put_nowait({"type": "artifact_write_completed", "repo": "/other"})
            q.put_nowait({"type": "artifact_write_completed", "repo": "/r"})
            EventBus._coalesce_queue(q, key)
            assert q.qsize() == 1
            await bus.unsubscribe(q)

        asyncio.run(_run())

    def test_publish_coalesces_duplicate_pending_events(self) -> None:
        async def _run() -> None:
            bus = EventBus()
            q = await bus.subscribe()
            q.put_nowait({"type": "artifact_write_completed", "repo": "/r"})
            q.put_nowait({"type": "artifact_write_completed", "repo": "/r"})
            await bus.publish({"type": "artifact_write_completed", "repo": "/r"})
            assert q.qsize() == 1
            await bus.unsubscribe(q)

        asyncio.run(_run())
