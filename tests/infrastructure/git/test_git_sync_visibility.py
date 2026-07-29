"""The enterprise sync must SURFACE why it skips a pull, not fail silently.

Before this, ``_ent_on_main`` returned bare when the upstream was unresolved, the
tree was dirty, or the mirror had diverged — so a deployment that never advanced
gave the GUI no signal. These tests drive the coroutines directly (no event-loop
fixture needed) and assert the dedicated ``sync_blocked`` event.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.git_sync_enterprise import ent_on_main, sync_enterprise

_BEHIND = "HEAD..origin/main"
_AHEAD = "origin/main..HEAD"


class _Bus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


def _patch_bus(monkeypatch: pytest.MonkeyPatch) -> _Bus:
    from src.infrastructure.gui.routers import events as ev

    bus = _Bus()
    monkeypatch.setattr(ev.event_bus, "publish", bus.publish)
    return bus


def _manager(monkeypatch: pytest.MonkeyPatch, responder) -> GitSyncManager:
    mgr = GitSyncManager([])

    async def fake_git(repo: Path, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        return responder(args)

    monkeypatch.setattr(mgr, "_git", fake_git)
    return mgr


def _blocked_reasons(bus: _Bus) -> list[str]:
    return [e["reason"] for e in bus.events if e["type"] == "sync_blocked"]


def test_missing_upstream_emits_blocked_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse":
            return (128, "", "fatal: no upstream configured")
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(ent_on_main(mgr, tmp_path / "repo-no-upstream"))
    assert bus.types() == ["sync_blocked"]
    assert "upstream" in bus.events[0]["reason"]

    # A second poll with the same condition must not re-spam the GUI.
    asyncio.run(ent_on_main(mgr, tmp_path / "repo-no-upstream"))
    assert len(bus.events) == 1


def test_diverged_mirror_emits_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse":
            return (0, "origin/main\n", "")
        if args[0] == "rev-list":
            return (0, "2\n", "")  # both ahead and behind non-zero → diverged
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(ent_on_main(mgr, tmp_path / "repo-diverged"))
    assert any("ahead" in r for r in _blocked_reasons(bus))


def test_dirty_tree_emits_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse":
            return (0, "origin/main\n", "")
        if args[0] == "rev-list":
            return (0, ("2" if args[2] == _BEHIND else "0") + "\n", "")
        if args[0] == "status":
            return (0, " M model/x.md\n", "")
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(ent_on_main(mgr, tmp_path / "repo-dirty"))
    assert any("uncommitted" in r for r in _blocked_reasons(bus))


def test_invalid_count_emits_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse":
            return (0, "origin/main\n", "")
        if args[0] == "rev-list":
            return (128, "", "fatal: bad revision")
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(ent_on_main(mgr, tmp_path / "repo-badref"))
    assert any("could not compute sync state" in r for r in _blocked_reasons(bus))


def test_clean_and_behind_pulls_to_completion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    from src.infrastructure.git import git_sync_m4
    from src.infrastructure.workspace.mutation_gate import _reset_for_test

    _reset_for_test()

    async def _fake_add_worktree(git_runner, repo, sha, *, timeout):
        return repo / ".arch-repo" / "sync-worktrees" / "fake-wt"

    monkeypatch.setattr(git_sync_m4, "add_detached_worktree", _fake_add_worktree)
    monkeypatch.setattr(git_sync_m4, "run_m4_pull", lambda *_args, **_kwargs: None)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse":
            if "--symbolic-full-name" in args:
                return (0, "origin/main\n", "")  # _upstream_ref
            if "--abbrev-ref" in args:
                return (0, "main\n", "")  # branch name
            return (0, "abc123def456\n", "")  # any sha
        if args[0] == "rev-list":
            return (0, ("3" if args[2] == _BEHIND else "0") + "\n", "")
        if args[0] == "status":
            return (0, "", "")
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(ent_on_main(mgr, tmp_path / "repo-clean"))
    assert "sync_pull_started" in bus.types()
    assert "sync_pull_completed" in bus.types()
    completed = next(e for e in bus.events if e["type"] == "sync_pull_completed")
    assert completed["commits_pulled"] == 3


def test_fetch_failure_is_surfaced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bus = _patch_bus(monkeypatch)

    def responder(args: tuple[str, ...]) -> tuple[int, str, str]:
        if args[0] == "rev-parse" and args[1] == "--git-dir":
            return (0, ".git\n", "")
        if args[0] == "fetch":
            return (1, "", "ssh: connect to host failed")
        return (0, "", "")

    mgr = _manager(monkeypatch, responder)

    asyncio.run(sync_enterprise(mgr, tmp_path / "repo-offline"))
    assert any("fetch" in r for r in _blocked_reasons(bus))
