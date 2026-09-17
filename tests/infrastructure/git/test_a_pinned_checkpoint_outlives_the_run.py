"""A checkpoint pinned under a ref can be restored long after the run that took it.

A promotion's checkpoint is a commit on the branch, un-committed on release. A data upgrade needs one
that outlives the run — `arch-repair upgrade --restore` may be asked for after the software moved on —
so the checkpoint is pinned under `refs/arch-repair/pre-upgrade/<name>`. Three properties, each on a
real repository: the objects survive `git gc --prune=now`; restoring returns a dirty tree byte-identical,
untracked file and modified tracked file included, with the branch reattached and the prior work
uncommitted again; and releasing the pin removes the ref and nothing else.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git.git_worktree_checkpoint import (
    checkpoint_from_ref,
    checkpoint_worktree,
    pin_checkpoint,
    release_pinned_checkpoint,
    release_worktree_checkpoint,
    restore_worktree_checkpoint,
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _snapshot(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): p.read_text(encoding="utf-8")
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }


@pytest.fixture()
def dirty(tmp_path: Path) -> Path:
    repo = tmp_path / "engagement"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "tracked.md").write_text("committed\n", encoding="utf-8")
    (repo / "model").mkdir()
    (repo / "model" / "a.md").write_text("a\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    (repo / "tracked.md").write_text("edited but not committed\n", encoding="utf-8")
    (repo / "untracked.md").write_text("never added\n", encoding="utf-8")
    return repo


def _pin(repo: Path, name: str = "20260917T000000Z") -> str:
    transient = checkpoint_worktree(repo)
    ref = pin_checkpoint(repo, transient, name)
    release_worktree_checkpoint(repo, transient)
    return ref


def test_pinning_leaves_the_branch_and_the_tree_where_they_were(dirty: Path) -> None:
    before = _snapshot(dirty)
    head = git(dirty, "rev-parse", "HEAD").stdout.strip()
    status = git(dirty, "status", "--porcelain").stdout

    _pin(dirty)

    assert _snapshot(dirty) == before
    assert git(dirty, "rev-parse", "HEAD").stdout.strip() == head
    assert git(dirty, "status", "--porcelain").stdout == status
    assert git(dirty, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"


def test_the_pinned_objects_survive_garbage_collection(dirty: Path) -> None:
    ref = _pin(dirty)

    assert git(dirty, "gc", "--prune=now", "-q").returncode == 0

    checkpoint = checkpoint_from_ref(dirty, ref)
    assert git(dirty, "cat-file", "-e", f"{checkpoint.checkpoint}^{{commit}}").returncode == 0
    assert checkpoint.branch == "main"


def test_restoring_from_the_ref_returns_the_dirty_tree_byte_identical(dirty: Path) -> None:
    before = _snapshot(dirty)
    status = git(dirty, "status", "--porcelain").stdout
    ref = _pin(dirty)
    # What an upgrade does: rewrite tracked content, add a file, delete one.
    (dirty / "tracked.md").write_text("migrated\n", encoding="utf-8")
    (dirty / "model" / "a.md").unlink()
    (dirty / "model" / "b.md").write_text("new\n", encoding="utf-8")
    (dirty / "untracked.md").write_text("clobbered\n", encoding="utf-8")

    restore_worktree_checkpoint(dirty, checkpoint_from_ref(dirty, ref))

    assert _snapshot(dirty) == before
    assert git(dirty, "status", "--porcelain").stdout == status
    assert git(dirty, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"


def test_a_clean_tree_pins_and_restores_too(tmp_path: Path) -> None:
    repo = tmp_path / "clean"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "f.md").write_text("v1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    ref = _pin(repo)
    (repo / "f.md").write_text("v2\n", encoding="utf-8")

    restore_worktree_checkpoint(repo, checkpoint_from_ref(repo, ref))

    assert (repo / "f.md").read_text(encoding="utf-8") == "v1\n"
    assert git(repo, "status", "--porcelain").stdout == ""


def test_releasing_the_pin_removes_the_ref_and_nothing_else(dirty: Path) -> None:
    before = _snapshot(dirty)
    ref = _pin(dirty)

    release_pinned_checkpoint(dirty, ref)

    assert git(dirty, "rev-parse", "--verify", "--quiet", ref).returncode != 0
    assert _snapshot(dirty) == before
    # Releasing twice is not an error: the second call finds nothing to forget.
    release_pinned_checkpoint(dirty, ref)


def test_a_missing_ref_is_refused_rather_than_guessed_at(dirty: Path) -> None:
    with pytest.raises(RuntimeError, match="No pinned checkpoint"):
        checkpoint_from_ref(dirty, "refs/arch-repair/pre-upgrade/never")
