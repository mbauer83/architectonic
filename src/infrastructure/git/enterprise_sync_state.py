"""Persistent versioned aggregate for the enterprise working-branch lifecycle and
its sync-health overlay.

Lifecycle (closed union): ``synced | accumulating | pending``.
Health overlay: healthy (``None``) or blocked — a closed reason code plus message
and observed UTC timestamp. The reason vocabulary is owned by the application
authorization policy; this module only serializes it.

Pure state module: typed load / transition / atomic persist only. It never
imports GUI caches or event buses — the sync orchestrator and the mutation
executor publish and invalidate through their own injected ports AFTER a
transition persists. A lifecycle transition never erases active health; old
unversioned state files load as healthy with their lifecycle preserved; corrupt
or torn files surface as blocked health (``state_file_corrupt``), never as a
silent synced state. All public functions are thread-safe.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast, get_args

from src.application.mutation_authorization import SyncHealthReason
from src.domain.clock import utc_now_iso

EnterpriseSyncStatus = Literal["synced", "accumulating", "pending"]

SCHEMA_VERSION = 2
_STATE_FILENAME = ".arch/enterprise-sync.json"
_VALID_REASONS: frozenset[str] = frozenset(get_args(SyncHealthReason))
_lock = threading.Lock()


@dataclass(frozen=True)
class SyncHealthRecord:
    reason: SyncHealthReason
    message: str
    observed_at: str


@dataclass(frozen=True)
class EnterpriseSyncState:
    status: EnterpriseSyncStatus = "synced"
    branch: str | None = None  # e.g. "arch/work-20260425-143012"
    branch_tip: str | None = None  # commit SHA recorded at push time
    pushed_at: str | None = None  # ISO-8601 timestamp of push
    commits_behind: int = 0  # commits on origin/main not yet on working branch
    health: SyncHealthRecord | None = None

    def is_synced(self) -> bool:
        return self.status == "synced"

    def is_accumulating(self) -> bool:
        return self.status == "accumulating"

    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_blocked(self) -> bool:
        return self.health is not None


@dataclass(frozen=True)
class SyncTransition:
    previous: EnterpriseSyncState
    current: EnterpriseSyncState

    @property
    def changed(self) -> bool:
        return self.previous != self.current


def _state_path(enterprise_root: Path) -> Path:
    return enterprise_root / _STATE_FILENAME


def _corrupt(message: str) -> EnterpriseSyncState:
    return EnterpriseSyncState(
        health=SyncHealthRecord(reason="state_file_corrupt", message=message, observed_at=utc_now_iso())
    )


def _parse_health(raw: object) -> SyncHealthRecord | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("health must be a mapping")
    reason = raw.get("reason")
    if not isinstance(reason, str) or reason not in _VALID_REASONS:
        raise ValueError(f"unknown health reason: {reason!r}")
    return SyncHealthRecord(
        reason=cast(SyncHealthReason, reason),
        message=str(raw.get("message", "")),
        observed_at=str(raw.get("observed_at", "")),
    )


def _parse(data: dict[str, object]) -> EnterpriseSyncState:
    status = data.get("status", "synced")
    if status not in ("synced", "accumulating", "pending"):
        raise ValueError(f"unknown lifecycle status: {status!r}")
    status = cast(EnterpriseSyncStatus, status)
    branch = data.get("branch")
    branch_tip = data.get("branch_tip")
    pushed_at = data.get("pushed_at")
    raw_behind = data.get("commits_behind", 0)
    return EnterpriseSyncState(
        status=status,
        branch=branch if isinstance(branch, str) else None,
        branch_tip=branch_tip if isinstance(branch_tip, str) else None,
        pushed_at=pushed_at if isinstance(pushed_at, str) else None,
        commits_behind=int(raw_behind) if isinstance(raw_behind, int | str) else 0,
        # Unversioned (pre-health) files load as healthy with lifecycle preserved.
        health=_parse_health(data.get("health")) if "version" in data else None,
    )


def _load_unlocked(enterprise_root: Path) -> EnterpriseSyncState:
    path = _state_path(enterprise_root)
    if not path.exists():
        return EnterpriseSyncState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state file is not a mapping")
        return _parse(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _corrupt(f"enterprise sync state file is unreadable: {exc}")


def _persist_unlocked(enterprise_root: Path, previous: EnterpriseSyncState, current: EnterpriseSyncState) -> None:
    """Atomic persist-on-change; the default aggregate is represented by no file."""
    if current == previous:
        return
    path = _state_path(enterprise_root)
    if current == EnterpriseSyncState():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    payload: dict[str, object] = {
        "version": SCHEMA_VERSION,
        "status": current.status,
        "branch": current.branch,
        "branch_tip": current.branch_tip,
        "pushed_at": current.pushed_at,
        "commits_behind": current.commits_behind,
        "health": None
        if current.health is None
        else {
            "reason": current.health.reason,
            "message": current.health.message,
            "observed_at": current.health.observed_at,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load(enterprise_root: Path) -> EnterpriseSyncState:
    with _lock:
        return _load_unlocked(enterprise_root)


_MTIME_CACHE: dict[Path, tuple[tuple[int, int] | None, EnterpriseSyncState]] = {}


def load_cached(enterprise_root: Path) -> EnterpriseSyncState:
    """mtime-validated read for hot paths (per-operation authority snapshots).

    One stat() per call; the parsed aggregate is reused until the file changes,
    so authorization stays O(1) and never re-parses on steady state.
    """
    with _lock:
        path = _state_path(enterprise_root)
        try:
            stat = path.stat()
            key: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            key = None
        cached = _MTIME_CACHE.get(enterprise_root)
        if cached is not None and cached[0] == key:
            return cached[1]
        state = _load_unlocked(enterprise_root)
        _MTIME_CACHE[enterprise_root] = (key, state)
        return state


def _transition(
    enterprise_root: Path, mutate: Callable[[EnterpriseSyncState], EnterpriseSyncState]
) -> SyncTransition:
    with _lock:
        previous = _load_unlocked(enterprise_root)
        current = mutate(previous)
        _persist_unlocked(enterprise_root, previous, current)
        return SyncTransition(previous=previous, current=current)


def replace_lifecycle(
    enterprise_root: Path,
    *,
    status: EnterpriseSyncStatus,
    branch: str | None = None,
    branch_tip: str | None = None,
    pushed_at: str | None = None,
    commits_behind: int = 0,
) -> SyncTransition:
    """Replace the whole lifecycle; active health is preserved untouched."""
    return _transition(
        enterprise_root,
        lambda state: replace(
            state,
            status=status,
            branch=branch,
            branch_tip=branch_tip,
            pushed_at=pushed_at,
            commits_behind=commits_behind,
        ),
    )


def clear_lifecycle(enterprise_root: Path) -> SyncTransition:
    """Return the lifecycle to synced (branch discarded/merged); health preserved."""
    return replace_lifecycle(enterprise_root, status="synced")


def record_commits_behind(enterprise_root: Path, commits_behind: int) -> SyncTransition:
    return _transition(enterprise_root, lambda state: replace(state, commits_behind=commits_behind))


def record_block(enterprise_root: Path, reason: SyncHealthReason, message: str) -> SyncTransition:
    """Set the health overlay; the lifecycle is preserved untouched.

    Re-recording the same reason+message is a no-op (the original observation
    timestamp stands), so steady-state polling never rewrites the file.
    """

    def mutate(state: EnterpriseSyncState) -> EnterpriseSyncState:
        if state.health is not None and (state.health.reason, state.health.message) == (reason, message):
            return state
        return replace(
            state, health=SyncHealthRecord(reason=reason, message=message, observed_at=utc_now_iso())
        )

    return _transition(enterprise_root, mutate)


def clear_block(enterprise_root: Path) -> SyncTransition:
    """Clear the health overlay; the lifecycle is preserved untouched."""
    return _transition(enterprise_root, lambda state: replace(state, health=None))
