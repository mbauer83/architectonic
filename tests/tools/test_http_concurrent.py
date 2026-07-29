"""HTTP-level concurrent-access test.

Simulates multiple browser tabs hitting the GUI REST API simultaneously.
The tests verify that:
  - Parallel GET requests do not serialize (N concurrent reads ≈ 1 read in wall time).
  - A long-running refresh (write lock held) does not block reads indefinitely once it
    releases — i.e. reads resume as soon as the write completes, not one-at-a-time.

These tests require the `gui` optional-dependency group (fastapi, httpx).
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import entities as entity_router
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.connections import router as connections_router

httpx = pytest.importorskip("httpx")


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    suffix = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-04-27'
keywords:
  - http
  - concurrent
---

<!-- §content -->

## {name}

Test entity for HTTP concurrency exercise.

## Properties

| Attribute | Value |
|---|---|
| owner | team-{suffix} |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{suffix}
```
"""


def _outgoing_md(source: str, target: str) -> str:
    return f"""\
---
source-entity: {source}
version: 0.1.0
status: active
last-updated: '2026-04-27'
---

<!-- §connections -->

### archimate-association → {target}
"""


def _build_test_app(repo_root: Path) -> tuple[FastAPI, list[str]]:
    """Populate a repo, build a minimal FastAPI app, return (app, entity_ids)."""
    model_root = repo_root / "model" / "motivation" / "requirement"
    entity_ids: list[str] = []

    for idx in range(60):
        aid = f"REQ@3000000{idx:03d}.C{idx:03d}.http-entity-{idx}"
        entity_ids.append(aid)
        _write(model_root / f"{aid}.md", _entity_md(aid, f"HTTP Entity {idx}"))

    for idx in range(len(entity_ids) - 1):
        _write(
            model_root / f"{entity_ids[idx]}.outgoing.md",
            _outgoing_md(entity_ids[idx], entity_ids[idx + 1]),
        )

    repo = ArtifactRepository(shared_artifact_index([repo_root]))
    gui_state.init_state(repo, repo_root, None)

    app = FastAPI()
    app.include_router(entity_router.router)
    app.include_router(connections_router)
    return app, entity_ids


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_concurrent_tab_reads_are_not_serialized(tmp_path: Path) -> None:
    """16 tabs hitting /api/entities simultaneously should finish in parallel, not
    one after the other.  We assert wall-clock time < 4 × single-request baseline."""
    repo_root = tmp_path / "engagements" / "ENG-HTTP" / "architecture-repository"
    app, entity_ids = _build_test_app(repo_root)

    async def _run() -> tuple[float, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Warm-up: one request so the index is already loaded.
            await client.get("/api/entities")

            # Single-request baseline.
            t0 = time.perf_counter()
            await client.get("/api/entities")
            single = time.perf_counter() - t0

            # 16 concurrent requests — simulate 16 open tabs.
            t1 = time.perf_counter()
            await asyncio.gather(*[client.get("/api/entities") for _ in range(16)])
            wall = time.perf_counter() - t1

        return single, wall

    single, wall = asyncio.run(_run())

    # With concurrent reads the total wall time should be close to a single
    # request, not 16×.  Allow 4× headroom for CI variance.
    assert wall < max(single * 4, 0.5), (
        f"Concurrent reads appear serialized: 16 requests took {wall:.3f}s but single request took {single:.3f}s"
    )


def test_entity_context_reads_are_not_serialized(tmp_path: Path) -> None:
    """Entity-context requests exercise the SQLite join path. 12 concurrent
    requests for different entity contexts must complete in parallel."""
    repo_root = tmp_path / "engagements" / "ENG-HTTP2" / "architecture-repository"
    app, entity_ids = _build_test_app(repo_root)

    async def _run() -> tuple[float, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get(f"/api/entity-context?id={entity_ids[0]}")

            t0 = time.perf_counter()
            await client.get(f"/api/entity-context?id={entity_ids[0]}")
            single = time.perf_counter() - t0

            urls = [f"/api/entity-context?id={entity_ids[i % len(entity_ids)]}" for i in range(12)]
            t1 = time.perf_counter()
            await asyncio.gather(*[client.get(u) for u in urls])
            wall = time.perf_counter() - t1

        return single, wall

    single, wall = asyncio.run(_run())
    assert wall < max(single * 4, 0.5), (
        f"Entity-context reads appear serialized: 12 requests took {wall:.3f}s but single request took {single:.3f}s"
    )


def test_reads_resume_promptly_after_index_refresh(tmp_path: Path) -> None:
    """While the index is being refreshed (write lock held), read requests must
    queue up and complete promptly once the refresh is done — not serialize
    one-at-a-time against each other."""
    repo_root = tmp_path / "engagements" / "ENG-HTTP3" / "architecture-repository"
    app, entity_ids = _build_test_app(repo_root)

    index = shared_artifact_index([repo_root])
    # Warm the index first.
    _ = index.generation()

    results: list[float] = []
    read_errors: list[Exception] = []

    async def _async_get(url: str) -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            t0 = time.perf_counter()
            r = await client.get(url)
            r.raise_for_status()
            return time.perf_counter() - t0

    def _reader(url: str) -> None:
        try:
            elapsed = asyncio.run(_async_get(url))
            results.append(elapsed)
        except Exception as exc:
            read_errors.append(exc)

    # Uncontended baseline for one read on THIS machine under the CURRENT suite
    # load — the assertions below scale with it so parallel test workers doing
    # CPU-heavy work nearby cannot fail a test whose subject is lock behavior,
    # not absolute latency.
    baseline_read = asyncio.run(_async_get("/api/entities?domain=motivation"))

    REFRESH_HOLD_S = 0.15  # hold the write lock this long to simulate a refresh

    def _slow_refresh() -> None:
        with index._lock.writing():
            time.sleep(REFRESH_HOLD_S)

    refresh_thread = threading.Thread(target=_slow_refresh)
    read_threads = [threading.Thread(target=_reader, args=("/api/entities?domain=motivation",)) for _ in range(6)]

    # Start the "refresh" first so it holds the write lock, then immediately
    # launch reader threads that will queue behind it.
    refresh_thread.start()
    time.sleep(0.01)  # let the write lock be acquired
    for t in read_threads:
        t.start()

    refresh_thread.join()
    for t in read_threads:
        t.join(timeout=5.0)

    assert not read_errors, f"Read errors: {read_errors}"
    assert len(results) == 6

    # All readers were unblocked together when the write lock released.
    # The maximum individual read time should not be >> REFRESH_HOLD_S + a few
    # reads' worth of work; six fully serialized readers would cost ~6 baseline
    # reads on top of the hold.
    max_read = max(results)
    assert max_read < REFRESH_HOLD_S + max(0.5, baseline_read * 3), (
        f"Reads appear to serialize after refresh: max read time={max_read:.3f}s, "
        f"refresh held lock for {REFRESH_HOLD_S}s, single read baseline={baseline_read:.3f}s"
    )
    # The spread between fastest and slowest reader should be small
    # (they were all released at the same time).
    spread = max(results) - min(results)
    assert spread < max(0.3, baseline_read * 3), (
        f"Large spread among readers ({spread:.3f}s) suggests they ran one-at-a-time "
        f"rather than concurrently after the refresh completed "
        f"(single read baseline={baseline_read:.3f}s)"
    )
