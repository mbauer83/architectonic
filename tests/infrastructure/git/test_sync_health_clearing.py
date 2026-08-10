"""Completed-gated health clearing: only a fully successful, fully grounded poll
(`ReconcileOutcome.completed` + a cleanly handled state) clears a persisted
health block — failed reconciles and faulted handlers never do.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.git_sync_enterprise import reconcile_state, sync_enterprise


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def clone_pair(tmp_path: Path) -> tuple[Path, Path]:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "T")
    (seed / "model").mkdir()
    (seed / "model" / "seed.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "seed")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "--bare", str(seed), str(origin)], check=True, capture_output=True)
    repo = tmp_path / "enterprise"
    subprocess.run(["git", "clone", str(origin), str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    return origin, repo


@pytest.fixture()
def quiet_bus(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []

    async def capture(event: dict[str, object]) -> None:
        events.append(event)

    from src.infrastructure.rest.routers import events as events_module

    monkeypatch.setattr(events_module.event_bus, "publish", capture)
    return events


class TestCompletedGatedClearing:
    def test_successful_poll_clears_a_prior_block(self, clone_pair, quiet_bus) -> None:
        _, repo = clone_pair
        enterprise_sync_state.record_block(repo, "fetch_failed", "was down")
        manager = GitSyncManager([])
        asyncio.run(sync_enterprise(manager, repo))
        assert enterprise_sync_state.load(repo).health is None

    def test_failed_fetch_records_and_never_clears(self, clone_pair, quiet_bus, monkeypatch) -> None:
        _, repo = clone_pair
        manager = GitSyncManager([])
        real_git = manager._git

        async def failing_fetch(root: Path, *args: str, timeout: float = 10.0):
            if args and args[0] == "fetch":
                return (1, "", "connection refused")
            return await real_git(root, *args, timeout=timeout)

        monkeypatch.setattr(manager, "_git", failing_fetch)
        asyncio.run(sync_enterprise(manager, repo))
        health = enterprise_sync_state.load(repo).health
        assert health is not None
        assert health.reason == "fetch_failed"

    def test_incomplete_reconcile_does_not_clear_a_prior_block(self, clone_pair, quiet_bus) -> None:
        """Checkout on main while the recorded working branch still holds unmerged
        work: reconcile reports completed=False and the block stays."""
        _, repo = clone_pair
        _git(repo, "checkout", "-b", "arch/work-unmerged")
        (repo / "model" / "work.md").write_text("work\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "unmerged work")
        _git(repo, "checkout", "main")
        enterprise_sync_state.replace_lifecycle(repo, status="accumulating", branch="arch/work-unmerged")

        manager = GitSyncManager([])
        outcome = asyncio.run(reconcile_state(manager, repo))
        assert outcome.completed is False
        health = enterprise_sync_state.load(repo).health
        assert health is not None
        assert health.reason == "diverged"

        asyncio.run(sync_enterprise(manager, repo))
        assert enterprise_sync_state.load(repo).health is not None

    def test_a_successful_fetch_clears_a_stale_fetch_failed_even_when_reconcile_stops_short(
        self, clone_pair, quiet_bus
    ) -> None:
        """The one reason a poll can disprove on its own.

        `fetch_failed` says the network was unreachable. The fetch at the top of this very poll
        succeeded, so the claim is no longer true — but clearing was gated on
        `ReconcileOutcome.completed`, which means something else entirely (the poll reached a fully
        grounded state). A single transient stall therefore stayed visible across every later healthy
        poll, with nothing in the record to say the network had recovered hours before.

        Same incomplete-reconcile setup as the test above, so the two differ only in *which* reason
        was persisted — which is the whole distinction being drawn.
        """
        _, repo = clone_pair
        _git(repo, "checkout", "-b", "arch/work-unmerged")
        (repo / "model" / "work.md").write_text("work\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "unmerged work")
        _git(repo, "checkout", "main")
        enterprise_sync_state.replace_lifecycle(repo, status="accumulating", branch="arch/work-unmerged")
        enterprise_sync_state.record_block(repo, "fetch_failed", "the network was down earlier")

        manager = GitSyncManager([])
        assert asyncio.run(reconcile_state(manager, repo)).completed is False

        asyncio.run(sync_enterprise(manager, repo))

        health = enterprise_sync_state.load(repo).health
        assert health is None or health.reason != "fetch_failed", (
            "a fetch that succeeded must retire the fetch_failed it disproves"
        )

    def test_a_reason_this_poll_raised_is_not_cleared_by_the_same_poll(
        self, clone_pair, quiet_bus
    ) -> None:
        """The guard on the fix: reconcile records `diverged` here, and the decision must be made
        from the health on disk *now*, not from the snapshot reconcile started with."""
        _, repo = clone_pair
        _git(repo, "checkout", "-b", "arch/work-unmerged")
        (repo / "model" / "work.md").write_text("work\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "unmerged work")
        _git(repo, "checkout", "main")
        enterprise_sync_state.replace_lifecycle(repo, status="accumulating", branch="arch/work-unmerged")
        enterprise_sync_state.record_block(repo, "fetch_failed", "stale, from an earlier poll")

        manager = GitSyncManager([])
        asyncio.run(sync_enterprise(manager, repo))

        # `diverged` is raised by this poll and describes something still true, so it survives.
        health = enterprise_sync_state.load(repo).health
        assert health is not None and health.reason == "diverged"

    def test_grounded_reconcile_reports_completed(self, clone_pair, quiet_bus) -> None:
        _, repo = clone_pair
        manager = GitSyncManager([])
        outcome = asyncio.run(reconcile_state(manager, repo))
        assert outcome.completed is True
        assert outcome.lifecycle.is_synced()

    def test_dirty_tree_skip_still_clears_remote_health(self, clone_pair, quiet_bus) -> None:
        """Dirty working tree is lifecycle state: the pull is skipped but a prior
        remote-relationship block (now recovered) is still cleared."""
        _, repo = clone_pair
        (repo / "model" / "dirty.md").write_text("dirty\n", encoding="utf-8")
        enterprise_sync_state.record_block(repo, "fetch_failed", "was down")
        manager = GitSyncManager([])
        asyncio.run(sync_enterprise(manager, repo))
        assert enterprise_sync_state.load(repo).health is None
