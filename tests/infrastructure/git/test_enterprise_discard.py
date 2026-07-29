"""Enterprise Discard: an idempotent desired-state transition over four ordered
postconditions (remote ref absent → checkout main → local branch absent →
aggregate cleared) on a REAL bare remote. Rejections are truthful (nothing to
discard, dirty tree = never silent success), fault injection after every step
converges on retry, and unrelated files survive.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_git_ops, enterprise_sync_state
from src.infrastructure.git.enterprise_git_ops import abandon_enterprise_branch
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

UNRELATED = "unrelated-keepsake.md"


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    engagement, enterprise = build_workflow_pair(tmp_path)
    origin = tmp_path / "enterprise-origin.git"
    (enterprise / UNRELATED).write_text("keep me\n", encoding="utf-8")
    git(enterprise, "add", UNRELATED)
    git(enterprise, "commit", "-m", "unrelated file")
    git(enterprise, "push", "origin", "main")
    return engagement, enterprise, origin


def _accumulate(enterprise: Path) -> str:
    branch = enterprise_git_ops.ensure_working_branch(enterprise)
    write_entity(enterprise, "REQ@1000001101.DisWrk.discard-work", "Discard Work")
    enterprise_git_ops.commit_enterprise_work(enterprise, "work to discard")
    return branch

def _submit(enterprise: Path) -> str:
    branch = _accumulate(enterprise)
    enterprise_git_ops.push_enterprise_branch(enterprise)
    return branch


def _remote_heads(origin: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(origin), "for-each-ref", "refs/heads"], check=True, capture_output=True, text=True
    ).stdout


def _assert_fully_discarded(enterprise: Path, origin: Path, branch: str) -> None:
    assert branch not in _remote_heads(origin)
    assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert branch not in git(enterprise, "branch", "--list", branch)
    assert enterprise_sync_state.load(enterprise) == enterprise_sync_state.EnterpriseSyncState()
    assert (enterprise / UNRELATED).read_text(encoding="utf-8") == "keep me\n"


class TestRejections:
    def test_nothing_to_discard_rejects(self, pair) -> None:
        _, enterprise, _ = pair
        with pytest.raises(ValueError, match="Nothing to discard"):
            abandon_enterprise_branch(enterprise)

    def test_dirty_tree_rejects_with_state_preserved(self, pair) -> None:
        _, enterprise, _ = pair
        branch = _accumulate(enterprise)
        write_entity(enterprise, "REQ@1000001102.DisDrt.dirty-probe", "Dirty Probe")
        with pytest.raises(ValueError, match="unsaved changes"):
            abandon_enterprise_branch(enterprise)
        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == branch
        assert enterprise_sync_state.load(enterprise).is_accumulating()


class TestLocalDiscard:
    def test_accumulating_discard_postconditions(self, pair) -> None:
        _, enterprise, origin = pair
        branch = _accumulate(enterprise)
        discarded = abandon_enterprise_branch(enterprise)
        assert discarded == branch
        _assert_fully_discarded(enterprise, origin, branch)


class TestPendingDiscard:
    def test_pending_discard_removes_the_remote_ref(self, pair) -> None:
        _, enterprise, origin = pair
        branch = _submit(enterprise)
        assert branch in _remote_heads(origin)
        abandon_enterprise_branch(enterprise)
        _assert_fully_discarded(enterprise, origin, branch)

    def test_initial_remote_deletion_failure_preserves_pending(self, pair, monkeypatch) -> None:
        """Ref still present after a failed deletion: report, no claimed withdrawal."""
        _, enterprise, origin = pair
        branch = _submit(enterprise)
        real_run = enterprise_git_ops._run

        def failing_delete(repo: Path, *args: str, **kwargs: object):
            if args[:3] == ("push", "origin", "--delete"):
                return (1, "", "injected remote failure")
            return real_run(repo, *args, **kwargs)

        monkeypatch.setattr(enterprise_git_ops, "_run", failing_delete)
        with pytest.raises(RuntimeError, match="delete remote branch"):
            abandon_enterprise_branch(enterprise)
        assert branch in _remote_heads(origin)
        assert enterprise_sync_state.load(enterprise).is_pending()

    def _converges_after(self, pair, monkeypatch, *, fail_step: Callable[[tuple[str, ...]], bool]) -> None:
        _, enterprise, origin = pair
        branch = _submit(enterprise)
        real_run = enterprise_git_ops._run
        state = {"failed": False}

        def inject(repo: Path, *args: str, **kwargs: object):
            if not state["failed"] and fail_step(args):
                state["failed"] = True
                return (1, "", "injected failure")
            return real_run(repo, *args, **kwargs)

        monkeypatch.setattr(enterprise_git_ops, "_run", inject)
        with pytest.raises(RuntimeError):
            abandon_enterprise_branch(enterprise)
        # Retry converges: already-satisfied steps (absent ref, on main) are successes.
        abandon_enterprise_branch(enterprise)
        _assert_fully_discarded(enterprise, origin, branch)

    def test_failure_after_remote_deletion_converges_on_retry(self, pair, monkeypatch) -> None:
        self._converges_after(pair, monkeypatch, fail_step=lambda args: args[:2] == ("checkout", "main"))

    def test_failure_after_checkout_converges_on_retry(self, pair, monkeypatch) -> None:
        self._converges_after(pair, monkeypatch, fail_step=lambda args: args[:2] == ("branch", "-D"))

    def test_failure_during_state_persistence_converges_on_retry(self, pair, monkeypatch) -> None:
        _, enterprise, origin = pair
        branch = _submit(enterprise)
        real_clear = enterprise_sync_state.clear_lifecycle
        state = {"failed": False}

        def failing_clear(root: Path):
            if not state["failed"]:
                state["failed"] = True
                raise OSError("injected persistence failure")
            return real_clear(root)

        monkeypatch.setattr(enterprise_git_ops.enterprise_sync_state, "clear_lifecycle", failing_clear)
        with pytest.raises(OSError):
            abandon_enterprise_branch(enterprise)
        # Aggregate is still pending: the transition is not claimed complete.
        assert enterprise_sync_state.load(enterprise).is_pending()
        abandon_enterprise_branch(enterprise)
        _assert_fully_discarded(enterprise, origin, branch)
