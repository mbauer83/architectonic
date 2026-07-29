"""Public coordination API for authoritative writes and background refreshes.

This module is the process-local orchestration boundary between two concerns:

- The authoritative write path, which applies targeted read-model updates
  synchronously and must preserve referential integrity.
- Background reconciliation, which absorbs out-of-band filesystem edits and
  periodic full refreshes without racing the write path.

"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bootstrap import normalize_mounts, service_key
from .events import (
    AuthoritativeIndexMutationCommitted,
    BackgroundIndexRefreshCompleted,
    WriteQueueStateChanged,
    event_bus,
)
from .versioning import ReadModelVersion

__all__ = [
    "get_write_queue_state_snapshot",
    "publish_authoritative_mutation",
    "publish_background_refresh_completed",
    "publish_write_queue_state",
    "suppress_redundant_refresh_paths",
    "wait_for_write_queue_drain",
]


def publish_write_queue_state(
    *,
    active_jobs: int,
    pending_jobs: int,
    active_tool_name: str | None = None,
    active_operation_id: str | None = None,
    active_phase: str | None = None,
) -> None:
    """Publish the current write-queue occupancy."""

    event_bus.publish(
        WriteQueueStateChanged(
            active_jobs=active_jobs,
            pending_jobs=pending_jobs,
            active_tool_name=active_tool_name,
            active_operation_id=active_operation_id,
            active_phase=active_phase,
        )
    )


def publish_authoritative_mutation(
    root_or_roots: Path | list[Path],
    *,
    changed_paths: list[Path],
    version: ReadModelVersion,
) -> None:
    """Publish a first-party write that already updated the authoritative index."""

    if not changed_paths:
        return
    event_bus.publish(
        AuthoritativeIndexMutationCommitted(
            roots_key=_roots_key_for(root_or_roots),
            changed_paths=tuple(str(path.resolve()) for path in changed_paths),
            version=version,
        )
    )


def publish_background_refresh_completed(
    root_or_roots: Path | list[Path],
    *,
    full_refresh: bool,
    changed_paths: list[Path],
    version: ReadModelVersion,
) -> None:
    """Publish completion of watcher- or interval-driven reconciliation refresh."""

    event_bus.publish(
        BackgroundIndexRefreshCompleted(
            roots_key=_roots_key_for(root_or_roots),
            full_refresh=full_refresh,
            changed_paths=tuple(str(path.resolve()) for path in changed_paths),
            version=version,
        )
    )


def wait_for_write_queue_drain(timeout_s: float | None = None) -> bool:
    """Block until the serialized write queue becomes idle."""

    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    with _write_state_cond:
        while _active_write_jobs > 0 or _pending_write_jobs > 0:
            if deadline is None:
                _write_state_cond.wait()
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _write_state_cond.wait(timeout=remaining)
    return True


def get_write_queue_state_snapshot() -> dict[str, str | int | None]:
    with _write_state_cond:
        return {
            "active_jobs": _active_write_jobs,
            "pending_jobs": _pending_write_jobs,
            "active_tool_name": _active_write_tool_name,
            "active_operation_id": _active_write_operation_id,
            "active_phase": _active_write_phase,
        }


def suppress_redundant_refresh_paths(
    root_or_roots: Path | list[Path],
    changed_paths: list[Path],
) -> list[Path]:
    """Drop watcher-detected paths already incorporated by authoritative writes."""

    if not changed_paths:
        return []
    now = time.monotonic()
    roots_key = _roots_key_for(root_or_roots)
    kept: list[Path] = []
    with _refresh_state_lock:
        state = _refresh_state.setdefault(roots_key, _RefreshSuppressionState())
        _prune_suppression_paths(state, now)
        for path in changed_paths:
            resolved = str(path.resolve())
            if resolved in state.pending_paths:
                state.pending_paths.pop(resolved, None)
                continue
            kept.append(path)
    return kept


@dataclass
class _RefreshSuppressionState:
    """Per-root suppression state for watcher echo events."""

    pending_paths: dict[str, float] = field(default_factory=dict)
    version: ReadModelVersion | None = None


_SUPPRESSION_TTL_S = 300.0
_write_state_cond = threading.Condition()
_active_write_jobs = 0
_pending_write_jobs = 0
_active_write_tool_name: str | None = None
_active_write_operation_id: str | None = None
_active_write_phase: str | None = None
_refresh_state_lock = threading.Lock()
_refresh_state: dict[str, _RefreshSuppressionState] = {}


def _roots_key_for(root_or_roots: Path | list[Path]) -> str:
    roots = root_or_roots if isinstance(root_or_roots, list) else [root_or_roots]
    mounts = normalize_mounts(roots)
    return service_key(mounts)


def _prune_suppression_paths(state: _RefreshSuppressionState, now: float) -> None:
    expired = [path for path, timestamp in state.pending_paths.items() if (now - timestamp) > _SUPPRESSION_TTL_S]
    for path in expired:
        state.pending_paths.pop(path, None)


def _handle_write_queue_state_changed(event: WriteQueueStateChanged) -> None:
    global _active_write_jobs, _pending_write_jobs
    global _active_write_tool_name, _active_write_operation_id, _active_write_phase
    with _write_state_cond:
        _active_write_jobs = event.active_jobs
        _pending_write_jobs = event.pending_jobs
        _active_write_tool_name = event.active_tool_name
        _active_write_operation_id = event.active_operation_id
        _active_write_phase = event.active_phase
        _write_state_cond.notify_all()


def _handle_authoritative_mutation_committed(event: AuthoritativeIndexMutationCommitted) -> None:
    now = time.monotonic()
    with _refresh_state_lock:
        state = _refresh_state.setdefault(event.roots_key, _RefreshSuppressionState())
        state.version = event.version
        for path in event.changed_paths:
            state.pending_paths[path] = now
        _prune_suppression_paths(state, now)


def _handle_background_refresh_completed(event: BackgroundIndexRefreshCompleted) -> None:
    with _refresh_state_lock:
        state = _refresh_state.setdefault(event.roots_key, _RefreshSuppressionState())
        state.version = event.version


event_bus.subscribe(WriteQueueStateChanged, _handle_write_queue_state_changed)
event_bus.subscribe(AuthoritativeIndexMutationCommitted, _handle_authoritative_mutation_committed)
event_bus.subscribe(BackgroundIndexRefreshCompleted, _handle_background_refresh_completed)
