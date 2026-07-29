"""The enterprise sync state file is a cache of intent — git reality must win.

Branch switches, merges, and deletions can happen outside the save/submit flow
(and a stale state file once even rode a PR into origin/main). Each poll must
re-ground the record instead of mis-dispatching the state machine on it.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.git_sync_enterprise import reconcile_state


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


@pytest.fixture
def ent(tmp_path: Path) -> Path:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "T")
    _commit_file(seed, "model/motivation/requirement/REQ@1.Seed01.base.md", "base\n", "seed")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "--bare", str(seed), str(origin))
    repo = tmp_path / "enterprise"
    _git(tmp_path, "clone", str(origin), str(repo))
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    return repo


def _reconcile(root: Path) -> enterprise_sync_state.EnterpriseSyncState:
    return asyncio.run(reconcile_state(GitSyncManager([]), root)).lifecycle


def _accumulating(branch: str) -> enterprise_sync_state.EnterpriseSyncState:
    return enterprise_sync_state.EnterpriseSyncState(status="accumulating", branch=branch)


def _save(root: Path, state: enterprise_sync_state.EnterpriseSyncState) -> None:
    enterprise_sync_state.replace_lifecycle(
        root,
        status=state.status,
        branch=state.branch,
        branch_tip=state.branch_tip,
        pushed_at=state.pushed_at,
        commits_behind=state.commits_behind,
    )


def test_consistent_state_is_untouched(ent: Path) -> None:
    _git(ent, "checkout", "-b", "arch/work-x")
    _save(ent, _accumulating("arch/work-x"))

    state = _reconcile(ent)

    assert state.is_accumulating()
    assert state.branch == "arch/work-x"


def test_untracked_manual_branch_is_adopted_as_accumulating(ent: Path) -> None:
    _git(ent, "checkout", "-b", "arch/work-manual")

    state = _reconcile(ent)

    assert state.is_accumulating()
    assert state.branch == "arch/work-manual"
    assert enterprise_sync_state.load(ent).branch == "arch/work-manual"


def test_recorded_branch_replaced_by_checked_out_branch(ent: Path) -> None:
    _git(ent, "checkout", "-b", "arch/work-new")
    _save(ent, _accumulating("arch/work-old"))

    state = _reconcile(ent)

    assert state.branch == "arch/work-new"
    assert state.is_accumulating()


def test_missing_recorded_branch_resets_to_synced(ent: Path) -> None:
    _save(ent, _accumulating("arch/work-gone"))

    state = _reconcile(ent)

    assert state.is_synced()
    assert enterprise_sync_state.load(ent).is_synced()


def test_externally_merged_branch_is_cleaned_up_from_main(ent: Path) -> None:
    # Work happens on the branch, gets pushed into origin/main out-of-band, and the
    # user switches back to main by hand — only the local branch + state remain.
    _git(ent, "checkout", "-b", "arch/work-merged")
    _commit_file(ent, "model/motivation/requirement/REQ@1.Work01.thing.md", "x\n", "work")
    _git(ent, "push", "origin", "arch/work-merged:main")
    _git(ent, "checkout", "main")
    _git(ent, "fetch", "origin")
    _save(ent, _accumulating("arch/work-merged"))

    state = _reconcile(ent)

    assert state.is_synced()
    assert "arch/work-merged" not in _git(ent, "branch", "--list")


def test_unmerged_branch_left_behind_on_main_blocks_instead_of_discarding(ent: Path) -> None:
    _git(ent, "checkout", "-b", "arch/work-open")
    _commit_file(ent, "model/motivation/requirement/REQ@1.Work02.open.md", "x\n", "unmerged work")
    _git(ent, "checkout", "main")
    _save(ent, _accumulating("arch/work-open"))

    state = _reconcile(ent)

    assert state.is_accumulating()
    assert state.branch == "arch/work-open"
    assert "arch/work-open" in _git(ent, "branch", "--list")


def test_detached_head_is_left_alone(ent: Path) -> None:
    sha = _git(ent, "rev-parse", "HEAD")
    _git(ent, "checkout", "--detach", sha)
    _save(ent, _accumulating("arch/work-x"))

    state = _reconcile(ent)

    assert state.is_accumulating()
    assert state.branch == "arch/work-x"
