"""The enterprise sync aggregate: versioned persistence, lifecycle/health
separation, old-file compatibility, corrupt-file surfacing, persist-on-change,
failed-persistence ordering, and concurrent update safety.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_sync_state as state_module
from src.infrastructure.git.enterprise_sync_state import (
    EnterpriseSyncState,
    clear_block,
    clear_lifecycle,
    load,
    record_block,
    record_commits_behind,
    replace_lifecycle,
)

_STATE_REL = ".arch/enterprise-sync.json"


def _state_file(root: Path) -> Path:
    return root / _STATE_REL


class TestOldFileCompatibility:
    def test_unversioned_file_loads_healthy_with_lifecycle_preserved(self, tmp_path: Path) -> None:
        payload = {"status": "pending", "branch": "arch/work-x", "branch_tip": "abc", "commits_behind": 3}
        _state_file(tmp_path).parent.mkdir(parents=True)
        _state_file(tmp_path).write_text(json.dumps(payload), encoding="utf-8")
        state = load(tmp_path)
        assert state.status == "pending"
        assert state.branch == "arch/work-x"
        assert state.commits_behind == 3
        assert state.health is None

    def test_versioned_round_trip_survives_restart(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-y")
        record_block(tmp_path, "fetch_failed", "origin unreachable")
        reloaded = load(tmp_path)
        assert reloaded.status == "accumulating"
        assert reloaded.branch == "arch/work-y"
        assert reloaded.health is not None
        assert reloaded.health.reason == "fetch_failed"
        assert reloaded.health.observed_at != ""


class TestLifecycleHealthSeparation:
    def test_lifecycle_transition_preserves_active_health(self, tmp_path: Path) -> None:
        record_block(tmp_path, "diverged", "mirror diverged")
        transition = replace_lifecycle(tmp_path, status="pending", branch="arch/work-z", branch_tip="def")
        assert transition.current.status == "pending"
        assert transition.current.health is not None
        assert transition.current.health.reason == "diverged"

    def test_clear_lifecycle_preserves_health(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-z")
        record_block(tmp_path, "upstream_missing", "no upstream")
        transition = clear_lifecycle(tmp_path)
        assert transition.current.status == "synced"
        assert transition.current.health is not None

    def test_record_block_preserves_lifecycle(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="pending", branch="arch/work-p", commits_behind=2)
        transition = record_block(tmp_path, "sync_state_unknown", "bad revision")
        assert transition.current.status == "pending"
        assert transition.current.commits_behind == 2

    def test_clear_block_touches_only_health(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-h")
        record_block(tmp_path, "fetch_failed", "down")
        transition = clear_block(tmp_path)
        assert transition.changed is True
        assert transition.current.health is None
        assert transition.current.status == "accumulating"


class TestPersistOnChange:
    def test_re_recording_the_same_block_is_a_no_op(self, tmp_path: Path) -> None:
        record_block(tmp_path, "fetch_failed", "origin unreachable")
        first = load(tmp_path)
        transition = record_block(tmp_path, "fetch_failed", "origin unreachable")
        assert transition.changed is False
        assert load(tmp_path).health == first.health

    def test_default_aggregate_is_represented_by_no_file(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-a")
        clear_lifecycle(tmp_path)
        assert not _state_file(tmp_path).exists()
        assert load(tmp_path) == EnterpriseSyncState()

    def test_clearing_health_keeps_a_non_default_lifecycle_file(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-b")
        record_block(tmp_path, "fetch_failed", "down")
        clear_block(tmp_path)
        assert _state_file(tmp_path).exists()
        assert load(tmp_path).status == "accumulating"

    def test_record_commits_behind_updates_only_that_field(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="pending", branch="arch/work-c", branch_tip="tip")
        transition = record_commits_behind(tmp_path, 5)
        assert transition.current.commits_behind == 5
        assert transition.current.branch_tip == "tip"


class TestCorruptFiles:
    def test_corrupt_file_surfaces_blocked_health_not_silent_synced(self, tmp_path: Path) -> None:
        _state_file(tmp_path).parent.mkdir(parents=True)
        _state_file(tmp_path).write_text("{ not json", encoding="utf-8")
        state = load(tmp_path)
        assert state.health is not None
        assert state.health.reason == "state_file_corrupt"

    def test_unknown_health_reason_is_corrupt(self, tmp_path: Path) -> None:
        payload = {"version": 2, "status": "synced", "health": {"reason": "made_up", "message": "?"}}
        _state_file(tmp_path).parent.mkdir(parents=True)
        _state_file(tmp_path).write_text(json.dumps(payload), encoding="utf-8")
        assert load(tmp_path).health is not None
        assert load(tmp_path).health.reason == "state_file_corrupt"

    def test_unknown_lifecycle_status_is_corrupt(self, tmp_path: Path) -> None:
        payload = {"version": 2, "status": "exploded"}
        _state_file(tmp_path).parent.mkdir(parents=True)
        _state_file(tmp_path).write_text(json.dumps(payload), encoding="utf-8")
        assert load(tmp_path).health is not None


class TestConcurrentUpdates:
    def test_concurrent_lifecycle_and_health_updates_lose_nothing(self, tmp_path: Path) -> None:
        replace_lifecycle(tmp_path, status="accumulating", branch="arch/work-t")

        def health_writer() -> None:
            for index in range(25):
                record_block(tmp_path, "fetch_failed", f"attempt {index}")

        def lifecycle_writer() -> None:
            for index in range(25):
                record_commits_behind(tmp_path, index)

        threads = [threading.Thread(target=health_writer), threading.Thread(target=lifecycle_writer)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        final = load(tmp_path)
        assert final.status == "accumulating"
        assert final.branch == "arch/work-t"
        assert final.health is not None
        assert final.health.message == "attempt 24"
        assert final.commits_behind == 24


class TestFailedPersistenceOrdering:
    def test_failed_persistence_raises_before_any_notification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The orchestrator's record path must surface persistence failures without
        publishing events or invalidating caches."""
        from src.infrastructure.git.git_sync import GitSyncManager

        invalidations: list[Path] = []
        published: list[dict[str, object]] = []

        async def capture(event: dict[str, object]) -> None:
            published.append(event)

        from src.infrastructure.gui.routers import events as events_module

        monkeypatch.setattr(events_module.event_bus, "publish", capture)

        def failing_record(root: Path, reason: str, message: str):
            raise OSError("disk full")

        monkeypatch.setattr(state_module, "record_block", failing_record)
        manager = GitSyncManager([], on_health_changed=invalidations.append)

        with pytest.raises(OSError):
            asyncio.run(manager._record_sync_blocked(tmp_path, "fetch_failed", "origin unreachable"))
        assert published == []
        assert invalidations == []

    def test_successful_persistence_invalidates_then_notifies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.git.git_sync import GitSyncManager

        invalidations: list[Path] = []
        published: list[dict[str, object]] = []

        async def capture(event: dict[str, object]) -> None:
            published.append(event)

        from src.infrastructure.gui.routers import events as events_module

        monkeypatch.setattr(events_module.event_bus, "publish", capture)
        manager = GitSyncManager([], on_health_changed=invalidations.append)

        asyncio.run(manager._record_sync_blocked(tmp_path, "fetch_failed", "origin unreachable"))
        assert invalidations == [tmp_path]
        assert [event["type"] for event in published] == ["sync_blocked"]
        assert load(tmp_path).health is not None
