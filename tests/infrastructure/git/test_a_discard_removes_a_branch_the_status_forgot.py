"""Discarding removes the remote branch whenever there is one, whatever the local status says.

The push updates origin before the aggregate is written, so a process that dies in between leaves the
branch published while the status still reads `accumulating`. Withdrawal used to consult the status:
it deleted the local branch, reported success, and left the branch on origin for a reviewer to find.

That is the "claimed withdrawal" the rest of the discard path is built to prevent — its steps already
treat *already absent* as success precisely so a retry converges — arrived through the status rather
than through the ref. Asking the remote is the fix, and it is the same correction the submission saga
makes for its own publication: state that describes a remote is derived from the remote.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import (
    enterprise_branch_lifecycle as lifecycle,
)
from src.infrastructure.git import (
    enterprise_sync_state,
    git_work_commits,
)
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    _, enterprise = build_workflow_pair(tmp_path)
    git(enterprise, "push", "origin", "main")
    return enterprise, tmp_path / "enterprise-origin.git"


def _accumulate(enterprise: Path) -> str:
    branch = lifecycle.ensure_working_branch(enterprise)
    write_entity(enterprise, "REQ@1000001401.OrpWrk.orphan-work", "Orphan Work")
    git_work_commits.commit_enterprise_work(enterprise, "work to submit")
    return branch


def _remote_heads(origin: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(origin), "for-each-ref", "refs/heads"], check=True, capture_output=True, text=True
    ).stdout


def _push_then_lose_the_status(enterprise: Path, monkeypatch) -> None:
    """The window: origin accepts the push, the process dies before the aggregate is written."""
    monkeypatch.setattr(
        enterprise_sync_state,
        "replace_lifecycle",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("injected crash before persisting")),
    )
    with pytest.raises(OSError):
        lifecycle.push_enterprise_branch(enterprise)
    monkeypatch.undo()


def test_the_window_is_real_before_asserting_what_happens_in_it(pair, monkeypatch) -> None:
    """Precondition. If the push did not land, or the status did, the test below proves nothing."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)

    _push_then_lose_the_status(enterprise, monkeypatch)

    assert branch in _remote_heads(origin), "the push must have landed"
    assert enterprise_sync_state.load(enterprise).status == "accumulating", "the status must not have"


def test_a_discard_in_that_window_removes_the_branch_from_origin(pair, monkeypatch) -> None:
    """The regression: it used to be left behind, and nothing later noticed."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)
    _push_then_lose_the_status(enterprise, monkeypatch)

    lifecycle.abandon_enterprise_branch(enterprise)

    assert branch not in _remote_heads(origin)
    assert branch not in git(enterprise, "branch", "--list", branch)
    assert enterprise_sync_state.load(enterprise) == enterprise_sync_state.EnterpriseSyncState()


def test_a_discard_with_nothing_on_origin_still_works(pair) -> None:
    """The ordinary case, unchanged: never pushed, so there is no remote ref to remove."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)

    lifecycle.abandon_enterprise_branch(enterprise)

    assert branch not in _remote_heads(origin)
    assert enterprise_sync_state.load(enterprise) == enterprise_sync_state.EnterpriseSyncState()


def test_a_discard_after_an_ordinary_submission_is_unchanged(pair) -> None:
    """The path that always worked keeps working — the condition widened, it did not move."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)
    lifecycle.push_enterprise_branch(enterprise)
    assert branch in _remote_heads(origin)

    lifecycle.abandon_enterprise_branch(enterprise)

    assert branch not in _remote_heads(origin)
    assert enterprise_sync_state.load(enterprise) == enterprise_sync_state.EnterpriseSyncState()


def test_a_failed_deletion_whose_ref_survives_reports_rather_than_claiming_withdrawal(
    pair, monkeypatch
) -> None:
    """Widening the condition must not weaken the refusal it guards."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)
    _push_then_lose_the_status(enterprise, monkeypatch)

    real = lifecycle.run_repo_git

    def failing_delete(repo, *args, **kwargs):
        if args[:3] == ("push", "origin", "--delete"):
            return (1, "", "injected remote failure")
        return real(repo, *args, **kwargs)

    monkeypatch.setattr(lifecycle, "run_repo_git", failing_delete)
    with pytest.raises(RuntimeError, match="delete remote branch"):
        lifecycle.abandon_enterprise_branch(enterprise)

    assert branch in _remote_heads(origin)
    assert enterprise_sync_state.load(enterprise).status == "accumulating"
