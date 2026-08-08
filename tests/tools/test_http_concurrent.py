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

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.connections.router import router as connections_router
from src.infrastructure.rest.routers.entities.router import router as entity_router
from tests.support.api_app import build_api_app

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

    app = build_api_app(entity_router, connections_router)
    return app, entity_ids


#: How many simultaneous readers to model — 16 open tabs, 12 context panes.
_TABS = 16
_CONTEXT_READS = 12

#: How unevenly concurrent requests may finish before they are judged to be queueing.
#:
#: Wall-clock totals cannot answer this question, which is why two earlier forms of these tests could
#: not fail for the reason they existed. The handlers are synchronous, so Starlette runs them in a
#: threadpool and they *do* overlap — but the work is SQLite plus Python serialization, which holds
#: the GIL, so 16 together measured 0.16 s against 0.036 s sequentially. Concurrency costs here
#: rather than pays, and — the fatal part — a lock that serialized every reader would make the total
#: *smaller*, so any upper bound on it passes precisely when the defect is present.
#:
#: What distinguishes the two is the spread. Queued readers finish one after another, so their
#: individual latencies fan out towards N x the first. Overlapping readers all wait on the same
#: contended resource and finish together, however slow that is. This bound is on the fan-out.
_LATENCY_SPREAD = 4.0


async def _concurrent_latencies(app: object, urls: list[str]) -> list[float]:
    """Each request's own latency when all are issued at once, after warming the index."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get(urls[0])

        async def timed(url: str) -> float:
            started = time.perf_counter()
            await client.get(url)
            return time.perf_counter() - started

        return list(await asyncio.gather(*[timed(url) for url in urls]))


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.verifies("REQ@1776637159.X5jYC0")
def test_concurrent_tab_reads_are_not_serialized(tmp_path: Path) -> None:
    """16 tabs hitting /api/entities at once must overlap rather than queue behind each other.

    The comparison is against the *same* requests run one after another, measured in the same
    process moments apart, rather than against a single-request baseline and an absolute ceiling.
    Both halves of that older form were wrong: an absolute 0.5 s floor was larger than the
    serialized time it was meant to catch — 16 × an 11 ms request is 176 ms, so a fully serialized
    server passed — while the same floor failed the test on an ordinarily busy machine, at 512 ms.
    A self-calibrating ratio cannot do either, because load moves both measurements together.
    """
    repo_root = tmp_path / "engagements" / "ENG-HTTP" / "architecture-repository"
    app, _entity_ids = _build_test_app(repo_root)

    latencies = asyncio.run(_concurrent_latencies(app, ["/api/entities"] * _TABS))

    assert max(latencies) < min(latencies) * _LATENCY_SPREAD, (
        f"Concurrent reads appear serialized: {_TABS} tabs finished between {min(latencies):.3f}s "
        f"and {max(latencies):.3f}s, a fan-out consistent with queueing rather than overlapping."
    )


def test_entity_context_reads_are_not_serialized(tmp_path: Path) -> None:
    """Entity-context requests exercise the SQLite join path. 12 concurrent
    requests for different entity contexts must complete in parallel."""
    repo_root = tmp_path / "engagements" / "ENG-HTTP2" / "architecture-repository"
    app, entity_ids = _build_test_app(repo_root)

    urls = [f"/api/entities/{entity_ids[i % len(entity_ids)]}/context" for i in range(_CONTEXT_READS)]
    latencies = asyncio.run(_concurrent_latencies(app, urls))

    assert max(latencies) < min(latencies) * _LATENCY_SPREAD, (
        f"Entity-context reads appear serialized: {_CONTEXT_READS} finished between "
        f"{min(latencies):.3f}s and {max(latencies):.3f}s."
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
