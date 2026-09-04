"""Aborting a promotion returns the checkout to its branch, whatever git was in the middle of.

The abort path used to restore two commits and nothing else. Measured against a conflicted rebase:
the checkout came back **detached**, `.git/rebase-merge` survived, and every later rebase failed with
"there is already a rebase-merge directory" — while the restore reported success throughout.

That is expensive rather than untidy. `submission_preflight` refuses a detached HEAD, so one failed
operation took down every submission, save and discard until a person intervened by hand; and because
the rebase state survived, retrying did not converge, which is the property the whole promotion design
rests on.

Real repositories with a real conflicted rebase: the subject is what git's own state directories do,
and a fake would be asserting the thing under test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git.git_worktree_checkpoint import (
    WorktreeCheckpoint,
    checkpoint_worktree,
    release_worktree_checkpoint,
    restore_worktree_checkpoint,
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


@pytest.fixture()
def diverged(tmp_path: Path) -> tuple[Path, str, str]:
    """A repo whose working branch conflicts with main, on the same file."""
    repo = tmp_path / "enterprise"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "f.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    main = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    git(repo, "checkout", "-qb", "arch/work")
    (repo / "f.md").write_text("theirs\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "work")
    git(repo, "checkout", "-q", main)
    (repo / "f.md").write_text("ours\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "other")
    git(repo, "checkout", "-q", "arch/work")
    return repo, main, "arch/work"


def _rebase_state_present(repo: Path) -> bool:
    return (repo / ".git" / "rebase-merge").exists() or (repo / ".git" / "rebase-apply").exists()


def test_the_conflict_actually_happens_before_anything_is_asserted_about_it(diverged) -> None:
    """Precondition. A rebase that cleanly succeeded would make every case below vacuous."""
    repo, main, _ = diverged
    checkpoint_worktree(repo)

    assert git(repo, "rebase", main).returncode != 0
    assert _rebase_state_present(repo)


class TestRestoringAfterAConflictedRebase:
    def test_the_checkout_comes_back_on_its_branch(self, diverged) -> None:
        """The regression: it came back detached, and `submission_preflight` refuses that."""
        repo, main, branch = diverged
        checkpoint = checkpoint_worktree(repo)
        git(repo, "rebase", main)

        restore_worktree_checkpoint(repo, checkpoint)

        assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == branch

    def test_the_rebase_state_is_gone(self, diverged) -> None:
        repo, main, _ = diverged
        checkpoint = checkpoint_worktree(repo)
        git(repo, "rebase", main)

        restore_worktree_checkpoint(repo, checkpoint)

        assert not _rebase_state_present(repo)

    def test_a_later_rebase_can_run_at_all(self, diverged) -> None:
        """Convergence on retry is what the promotion design rests on. It used to fail with
        `fatal: It seems that there is already a rebase-merge directory`."""
        repo, main, _ = diverged
        checkpoint = checkpoint_worktree(repo)
        git(repo, "rebase", main)
        restore_worktree_checkpoint(repo, checkpoint)

        retried = git(repo, "rebase", main)

        assert "already a rebase-merge directory" not in retried.stderr
        assert retried.returncode != 128

    def test_uncommitted_work_is_uncommitted_again(self, diverged) -> None:
        """The property the abort path always had, and must keep."""
        repo, main, _ = diverged
        (repo / "dirty.md").write_text("not saved yet\n", encoding="utf-8")
        checkpoint = checkpoint_worktree(repo)
        git(repo, "rebase", main)

        restore_worktree_checkpoint(repo, checkpoint)

        assert (repo / "dirty.md").read_text(encoding="utf-8") == "not saved yet\n"
        assert "dirty.md" in git(repo, "status", "--porcelain").stdout


class TestTheOrdinaryAbort:
    def test_a_clean_abort_still_restores_the_tree(self, diverged) -> None:
        """No operation in progress — the path that always worked."""
        repo, _main, branch = diverged
        (repo / "dirty.md").write_text("not saved yet\n", encoding="utf-8")
        checkpoint = checkpoint_worktree(repo)
        (repo / "promoted.md").write_text("written by the promotion\n", encoding="utf-8")

        restore_worktree_checkpoint(repo, checkpoint)

        assert not (repo / "promoted.md").exists()
        assert (repo / "dirty.md").read_text(encoding="utf-8") == "not saved yet\n"
        assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == branch

    def test_the_success_path_leaves_the_work_unsaved(self, diverged) -> None:
        repo, _main, _branch = diverged
        (repo / "dirty.md").write_text("not saved yet\n", encoding="utf-8")
        checkpoint = checkpoint_worktree(repo)

        release_worktree_checkpoint(repo, checkpoint)

        assert "dirty.md" in git(repo, "status", "--porcelain").stdout


class TestWhatTheCheckpointRecords:
    def test_it_records_the_branch_it_was_taken_on(self, diverged) -> None:
        repo, _main, branch = diverged

        assert checkpoint_worktree(repo).branch == branch

    def test_a_checkout_already_detached_records_no_branch(self, diverged) -> None:
        """A state to restore faithfully, not to repair: the caller detached it deliberately."""
        repo, _main, _branch = diverged
        git(repo, "checkout", "-q", "--detach")

        checkpoint = checkpoint_worktree(repo)

        assert checkpoint.branch is None

    def test_a_clean_tree_checkpoints_as_head_itself(self, diverged) -> None:
        repo, _main, _branch = diverged
        head = git(repo, "rev-parse", "HEAD").stdout.strip()

        checkpoint = checkpoint_worktree(repo)

        assert checkpoint == WorktreeCheckpoint(branch="arch/work", head=head, checkpoint=head)
