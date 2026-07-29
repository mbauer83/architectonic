"""Enterprise merge auto-detection must also cover branches merged WITHOUT submit.

Reproduces the production gap: a user pushed the accumulating working branch and
merged it via a PR by hand, so the state never reached PENDING — and the watcher
only fetched and counted divergence forever instead of switching back to main.
The accumulating handler must now detect the merge (real commits + clean tree +
empty content diff) and run the same transition as the pending handler.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.git_sync_enterprise import ent_accumulating


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit_file(repo: Path, rel: str, content: str, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)


def _clone_pair(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin with one commit on main, plus a local enterprise clone."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "T")
    _commit_file(seed, "model/motivation/requirement/REQ@1.Seed01.base.md", "base\n", "seed")

    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "--bare", str(seed), str(origin))

    ent = tmp_path / "enterprise"
    _git(tmp_path, "clone", str(origin), str(ent))
    _git(ent, "config", "user.email", "t@example.invalid")
    _git(ent, "config", "user.name", "T")
    return origin, ent


def _start_work_branch(ent: Path, branch: str) -> None:
    _git(ent, "checkout", "-b", branch)
    _commit_file(ent, "model/motivation/requirement/REQ@1.Work01.promoted.md", "promoted\n", "promote work")
    enterprise_sync_state.replace_lifecycle(ent, status="accumulating", branch=branch)


def _merge_on_origin(origin: Path, ent: Path, branch: str) -> None:
    """Push the branch and merge it into origin/main out-of-band (the manual PR)."""
    _git(ent, "push", "origin", branch)
    merger = origin.parent / "merger"
    _git(origin.parent, "clone", str(origin), str(merger))
    _git(merger, "config", "user.email", "t@example.invalid")
    _git(merger, "config", "user.name", "T")
    _git(merger, "merge", "--no-ff", f"origin/{branch}", "-m", "Merge pull request")
    _git(merger, "push", "origin", "main")
    _git(ent, "fetch", "origin")


class _Bus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch) -> _Bus:
    from src.infrastructure.gui.routers import events as ev

    fake = _Bus()
    monkeypatch.setattr(ev.event_bus, "publish", fake.publish)
    return fake


def _run_accumulating(ent: Path) -> None:
    mgr = GitSyncManager([])
    state = enterprise_sync_state.load(ent)
    asyncio.run(ent_accumulating(mgr, ent, state))


def test_manual_merge_while_accumulating_switches_back_to_main(tmp_path: Path, bus: _Bus) -> None:
    origin, ent = _clone_pair(tmp_path)
    _start_work_branch(ent, "arch/work-test")
    _merge_on_origin(origin, ent, "arch/work-test")

    _run_accumulating(ent)

    assert _git(ent, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert "arch/work-test" not in _git(ent, "branch", "--list")
    assert _git(ent, "rev-parse", "HEAD") == _git(ent, "rev-parse", "origin/main")
    assert enterprise_sync_state.load(ent).is_synced()
    assert "sync_enterprise_merged" in bus.types()


def test_unmerged_divergence_still_only_reports(tmp_path: Path, bus: _Bus) -> None:
    origin, ent = _clone_pair(tmp_path)
    _start_work_branch(ent, "arch/work-test")
    # origin/main moves with UNRELATED content — the branch was not merged.
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(origin), str(other))
    _git(other, "config", "user.email", "t@example.invalid")
    _git(other, "config", "user.name", "T")
    _commit_file(other, "model/motivation/requirement/REQ@1.Other1.unrelated.md", "x\n", "other work")
    _git(other, "push", "origin", "main")
    _git(ent, "fetch", "origin")

    _run_accumulating(ent)

    assert _git(ent, "rev-parse", "--abbrev-ref", "HEAD") == "arch/work-test"
    assert bus.types() == ["sync_enterprise_diverged"]
    assert enterprise_sync_state.load(ent).is_accumulating()


def test_dirty_tree_defers_the_switch(tmp_path: Path, bus: _Bus) -> None:
    origin, ent = _clone_pair(tmp_path)
    _start_work_branch(ent, "arch/work-test")
    _merge_on_origin(origin, ent, "arch/work-test")
    (ent / "model" / "unsaved.md").write_text("unsaved work\n", encoding="utf-8")

    _run_accumulating(ent)

    assert _git(ent, "rev-parse", "--abbrev-ref", "HEAD") == "arch/work-test"
    assert enterprise_sync_state.load(ent).is_accumulating()
    assert "sync_enterprise_merged" not in bus.types()


def test_runtime_state_file_alone_does_not_count_as_dirty(tmp_path: Path, bus: _Bus) -> None:
    origin, ent = _clone_pair(tmp_path)
    _start_work_branch(ent, "arch/work-test")
    _merge_on_origin(origin, ent, "arch/work-test")
    # The state file is rewritten by the watcher itself on every divergence poll.
    state_file = ent / ".arch" / "enterprise-sync.json"
    state_file.write_text(json.dumps({"status": "accumulating", "branch": "arch/work-test"}))

    _run_accumulating(ent)

    assert _git(ent, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert "sync_enterprise_merged" in bus.types()


def test_fresh_branch_without_commits_never_transitions(tmp_path: Path, bus: _Bus) -> None:
    origin, ent = _clone_pair(tmp_path)
    _git(ent, "checkout", "-b", "arch/work-test")
    enterprise_sync_state.replace_lifecycle(ent, status="accumulating", branch="arch/work-test")
    # origin/main gains a commit that does not touch model/docs/diagram-catalog,
    # so the content diff is empty — but the branch carries no work to merge.
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(origin), str(other))
    _git(other, "config", "user.email", "t@example.invalid")
    _git(other, "config", "user.name", "T")
    _commit_file(other, "README.md", "readme\n", "docs housekeeping")
    _git(other, "push", "origin", "main")
    _git(ent, "fetch", "origin")

    _run_accumulating(ent)

    assert _git(ent, "rev-parse", "--abbrev-ref", "HEAD") == "arch/work-test"
    assert enterprise_sync_state.load(ent).is_accumulating()
    assert "sync_enterprise_merged" not in bus.types()
