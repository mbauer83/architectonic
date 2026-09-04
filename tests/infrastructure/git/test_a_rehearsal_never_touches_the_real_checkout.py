"""Attempting a rebase in a rehearsal worktree leaves the enterprise checkout untouched.

The whole point: a rebase has to be attempted to know whether it applies, and attempting it in the
checkout a reader is looking at is how a conflict came to leave state there. So every case below
checks the *enterprise* checkout after something went wrong in the rehearsal.

Real worktrees on real repositories. A worktree's defining property is that it has its own index and
HEAD while sharing the object database, and a fake would assert exactly the thing under test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git.rehearsal_worktree import (
    RehearsalUnavailable,
    prune_stale_worktrees,
    rehearsal_worktree,
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


@pytest.fixture()
def diverged(tmp_path: Path) -> tuple[Path, str, str]:
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


def _state(repo: Path) -> dict[str, object]:
    return {
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
        "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
        "status": git(repo, "status", "--porcelain").stdout,
        "rebase": (repo / ".git" / "rebase-merge").exists(),
    }


class TestTheCheckoutIsUntouched:
    def test_a_conflicted_rebase_in_the_rehearsal_leaves_no_trace(self, diverged) -> None:
        repo, main, branch = diverged
        before = _state(repo)

        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            conflicted = git(rehearsal.path, "rebase", main)
            assert conflicted.returncode != 0, "the rehearsal must actually conflict"
            assert (rehearsal.path / ".git").exists(), "a worktree has its own git state"

        assert _state(repo) == before

    def test_uncommitted_work_in_the_checkout_survives_a_rehearsal(self, diverged) -> None:
        """The reader's unsaved work is the thing most obviously at risk from an in-place attempt."""
        repo, main, branch = diverged
        (repo / "dirty.md").write_text("not saved yet\n", encoding="utf-8")

        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            git(rehearsal.path, "rebase", main)

        assert (repo / "dirty.md").read_text(encoding="utf-8") == "not saved yet\n"

    def test_the_rehearsal_starts_from_the_commit_it_was_asked_for(self, diverged) -> None:
        repo, _main, branch = diverged
        wanted = git(repo, "rev-parse", branch).stdout.strip()

        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            assert git(rehearsal.path, "rev-parse", "HEAD").stdout.strip() == wanted

    def test_the_rehearsal_is_detached_so_it_does_not_lock_the_branch(self, diverged) -> None:
        """Two worktrees cannot hold one branch, and the branch a rehearsal is about is the one the
        enterprise checkout has — so checking it out would refuse before anything was attempted."""
        repo, _main, branch = diverged

        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            assert git(rehearsal.path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "HEAD"
            assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == branch


class TestItIsAlwaysRemoved:
    def test_after_an_ordinary_exit(self, diverged) -> None:
        repo, _main, branch = diverged
        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            path = rehearsal.path

        assert not path.exists()
        assert str(path) not in git(repo, "worktree", "list").stdout

    def test_after_an_exception(self, diverged) -> None:
        """A rehearsal that raises must not leave a checkout behind for the next one to trip over."""
        repo, _main, branch = diverged
        with pytest.raises(ZeroDivisionError):
            with rehearsal_worktree(repo, start_point=branch) as rehearsal:
                path = rehearsal.path
                raise ZeroDivisionError

        assert not path.exists()
        assert str(path) not in git(repo, "worktree", "list").stdout

    def test_even_when_it_is_left_mid_rebase(self, diverged) -> None:
        """The expected state on the failure path — removal must not need a tidy tree."""
        repo, main, branch = diverged
        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            path = rehearsal.path
            git(path, "rebase", main)

        assert not path.exists()
        assert str(path) not in git(repo, "worktree", "list").stdout

    def test_even_when_it_is_left_dirty(self, diverged, caplog) -> None:
        """Measured: `git worktree remove` refuses a worktree with modified or untracked files —
        rc 128, `contains modified or untracked files`. A rehearsal is *expected* to leave both.

        The directory goes either way, because removal is belt-and-braces: git's own removal, then
        the temporary directory, then a prune. What `--force` buys is the difference between a quiet
        exit and a warning on every rehearsal that did its job — which is what the assertion below
        is about, since the paths are gone in both cases.
        """
        repo, _main, branch = diverged
        with caplog.at_level("WARNING"):
            with rehearsal_worktree(repo, start_point=branch) as rehearsal:
                path = rehearsal.path
                (path / "f.md").write_text("modified by the rehearsal\n", encoding="utf-8")
                (path / "left-behind.md").write_text("untracked\n", encoding="utf-8")

        assert not path.exists()
        assert str(path) not in git(repo, "worktree", "list").stdout
        assert "Could not remove the rehearsal worktree" not in caplog.text

    def test_two_rehearsals_in_a_row_both_work(self, diverged) -> None:
        repo, main, branch = diverged
        for _ in range(2):
            with rehearsal_worktree(repo, start_point=branch) as rehearsal:
                git(rehearsal.path, "rebase", main)

        assert git(repo, "worktree", "list").stdout.count("\n") == 1


class TestPruningAnInterruptedRun:
    def test_a_directory_removed_behind_gits_back_is_forgotten(self, diverged) -> None:
        """What a killed process leaves: the files gone, the administrative entry behind."""
        repo, _main, branch = diverged
        with rehearsal_worktree(repo, start_point=branch) as rehearsal:
            leaked = rehearsal.path
            subprocess.run(["rm", "-rf", str(leaked)], check=True)
            registered_before = git(repo, "worktree", "list").stdout

        assert str(leaked) in registered_before

        prune_stale_worktrees(repo)

        assert str(leaked) not in git(repo, "worktree", "list").stdout

    def test_pruning_a_repository_with_nothing_to_prune_changes_nothing(self, diverged) -> None:
        repo, _main, _branch = diverged
        before = git(repo, "worktree", "list").stdout

        prune_stale_worktrees(repo)

        assert git(repo, "worktree", "list").stdout == before

    def test_it_also_forgets_an_interrupted_sync_worktree(self, diverged) -> None:
        """The sync manager makes detached worktrees under `.arch-repo/sync-worktrees/` and nothing
        pruned those before. One startup repair covers every worktree this product creates."""
        repo, _main, _branch = diverged
        sync_worktree = repo / ".arch-repo" / "sync-worktrees" / "sync-abc123"
        sync_worktree.parent.mkdir(parents=True)
        git(repo, "worktree", "add", "--detach", str(sync_worktree), "HEAD")
        subprocess.run(["rm", "-rf", str(sync_worktree)], check=True)
        assert str(sync_worktree) in git(repo, "worktree", "list").stdout

        prune_stale_worktrees(repo)

        assert str(sync_worktree) not in git(repo, "worktree", "list").stdout

    def test_a_worktree_a_person_still_has_on_disk_is_not_touched(self, diverged, tmp_path) -> None:
        """Only what git itself reports as prunable — someone else's worktree is not ours to forget."""
        repo, _main, _branch = diverged
        theirs = tmp_path / "someone-elses-worktree"
        git(repo, "worktree", "add", "--detach", str(theirs), "HEAD")

        prune_stale_worktrees(repo)

        assert str(theirs) in git(repo, "worktree", "list").stdout
        assert theirs.exists()


def test_a_start_point_that_does_not_exist_is_refused_without_creating_anything(diverged) -> None:
    repo, _main, _branch = diverged
    before = git(repo, "worktree", "list").stdout

    with pytest.raises(RehearsalUnavailable, match="rehearsal worktree"):
        with rehearsal_worktree(repo, start_point="no-such-commit"):
            pass

    assert git(repo, "worktree", "list").stdout == before
