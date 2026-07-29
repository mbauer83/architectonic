"""Sync-status read model: cached measurements, fresh authority.

Only the EXPENSIVE git probes (dirty flags, ahead counts) are cached, with
singleflight refresh and explicit invalidation. Everything cheap is composed
per request: the persisted lifecycle+health aggregate and the per-intent
authority projection from the executor's snapshot provider — so a live
``gate.blocking_writes()`` transition or a persisted-health change is visible
to the very next request with no TTL and no ``write_block_manager`` shims.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from src.config.repo_paths import DIAGRAM_CATALOG, DOCS, MODEL

_MAX_STALE_S = 120.0
_lock = asyncio.Lock()
_refresh_task: asyncio.Task[dict[str, Any]] | None = None
_cached_value: dict[str, Any] | None = None
_cached_at_monotonic = 0.0
_dirty = True


async def _measure() -> dict[str, Any]:
    """Expensive git probes only — the cacheable part of the status."""
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.gui.routers import state as s

    measurements: dict[str, Any] = {"engagement_dirty": None, "enterprise_dirty": None, "commits_ahead": None}

    eng_root = s.maybe_engagement_root()
    if eng_root is not None:
        measurements["engagement_dirty"] = await asyncio.to_thread(
            enterprise_git_ops.has_uncommitted_changes, eng_root, MODEL, DOCS, DIAGRAM_CATALOG
        )

    ent_root = s.maybe_enterprise_root()
    if ent_root is not None:
        measurements["enterprise_dirty"] = await asyncio.to_thread(
            enterprise_git_ops.has_uncommitted_changes, ent_root
        )
        # Live ahead-count in every mode (including read-only): behind-state must be truthful.
        measurements["commits_ahead"] = await asyncio.to_thread(enterprise_git_ops.commits_ahead_of_main, ent_root)

    return measurements


async def get_sync_status() -> dict[str, Any]:
    measurements = await _cached_measurements()
    return _compose(measurements)


def _compose(measurements: dict[str, Any]) -> dict[str, Any]:
    """Fresh lifecycle + health + authority over the cached measurements."""
    from src.infrastructure.git import enterprise_sync_state
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers._sync_authority import authority_projection
    from src.infrastructure.gui.routers.sync import _status_label
    from src.infrastructure.write.mutation_executor_registry import authorization_snapshot

    out: dict[str, Any] = {"engagement": None, "enterprise": None}

    if s.maybe_engagement_root() is not None:
        out["engagement"] = {"has_uncommitted_changes": bool(measurements["engagement_dirty"])}

    ent_root = s.maybe_enterprise_root()
    if ent_root is not None:
        sync_state = enterprise_sync_state.load_cached(ent_root)
        health = sync_state.health
        info: dict[str, Any] = {
            "status": sync_state.status,
            "label": _status_label(sync_state.status),
            "branch": sync_state.branch,
            "branch_tip": sync_state.branch_tip,
            "pushed_at": sync_state.pushed_at,
            "commits_behind": sync_state.commits_behind,
            "has_uncommitted_changes": bool(measurements["enterprise_dirty"]),
            "health": None
            if health is None
            else {"reason": health.reason, "message": health.message, "observed_at": health.observed_at},
        }
        if sync_state.is_accumulating():
            info["commits_ahead"] = measurements["commits_ahead"]
        out["enterprise"] = info

    out["authority"] = authority_projection(authorization_snapshot())
    return out


async def _cached_measurements() -> dict[str, Any]:
    global _refresh_task
    now = time.monotonic()
    cached = _cached_value
    if cached is not None and not _dirty and (now - _cached_at_monotonic) < _MAX_STALE_S:
        return cached

    async with _lock:
        now = time.monotonic()
        cached = _cached_value
        if cached is not None and not _dirty and (now - _cached_at_monotonic) < _MAX_STALE_S:
            return cached
        if _refresh_task is None or _refresh_task.done():
            _refresh_task = asyncio.create_task(_refresh_now(), name="sync-status-refresh")
        task = _refresh_task

    return await task


async def _refresh_now() -> dict[str, Any]:
    global _cached_value, _cached_at_monotonic, _dirty
    value = await _measure()
    async with _lock:
        _cached_value = value
        _cached_at_monotonic = time.monotonic()
        _dirty = False
    return value


def invalidate_sync_status_cache(*, repo: Path | None = None) -> None:
    """Mark the cached measurements dirty.

    The optional repo path is reserved for future per-repo segmentation.
    """

    del repo
    global _dirty
    _dirty = True


def reset_sync_status_cache() -> None:
    """Testing helper to reset process-local cache state."""

    global _refresh_task, _cached_value, _cached_at_monotonic, _dirty
    _refresh_task = None
    _cached_value = None
    _cached_at_monotonic = 0.0
    _dirty = True
