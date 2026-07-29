from __future__ import annotations

import asyncio

from src.infrastructure.gui.routers import sync_status_cache
from src.infrastructure.gui.routers.events import EventBus


def test_sync_status_cache_coalesces_concurrent_refreshes(monkeypatch) -> None:
    """Only the EXPENSIVE measurements are cached with singleflight — the
    lifecycle/authority composition happens fresh per request."""
    sync_status_cache.reset_sync_status_cache()
    calls = 0

    async def fake_measure() -> dict[str, object]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"engagement_dirty": False, "enterprise_dirty": None, "commits_ahead": None}

    monkeypatch.setattr(sync_status_cache, "_measure", fake_measure)

    async def run() -> list[dict[str, object]]:
        return await asyncio.gather(*[sync_status_cache._cached_measurements() for _ in range(25)])

    results = asyncio.run(run())

    assert calls == 1
    assert len(results) == 25
    assert all(result["engagement_dirty"] is False for result in results)


def test_sync_status_cache_recomputes_after_invalidation(monkeypatch) -> None:
    sync_status_cache.reset_sync_status_cache()
    calls = 0

    async def fake_measure() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"engagement_dirty": bool(calls % 2), "enterprise_dirty": None, "commits_ahead": None}

    monkeypatch.setattr(sync_status_cache, "_measure", fake_measure)

    first = asyncio.run(sync_status_cache._cached_measurements())
    second = asyncio.run(sync_status_cache._cached_measurements())
    sync_status_cache.invalidate_sync_status_cache()
    third = asyncio.run(sync_status_cache._cached_measurements())

    assert calls == 2
    assert first == second
    assert third != second


def test_event_bus_coalesces_redundant_status_events() -> None:
    async def run() -> None:
        bus = EventBus()
        queue = await bus.subscribe()
        await bus.publish({"type": "sync_status_changed", "repo": "/tmp/repo-a", "seq": 1})
        await bus.publish({"type": "sync_status_changed", "repo": "/tmp/repo-a", "seq": 2})
        await bus.publish({"type": "artifact_write_completed"})
        await bus.publish({"type": "artifact_write_completed"})

        assert queue.qsize() == 2
        first = await queue.get()
        second = await queue.get()
        assert first["type"] == "sync_status_changed"
        assert first["seq"] == 2
        assert second["type"] == "artifact_write_completed"

    asyncio.run(run())
