"""A submission a previous process left in flight is settled against the remote, or left alone.

Every arm of the phase gets an answer, because reconciliation dispatches on it: a completed one is
settled, a pushed one is awaiting its changes being marked, and a prepared one is the interesting
case — the push may or may not have landed, and only the remote knows.

**A remote that cannot be reached changes nothing.** Absence of evidence about a branch is equally
consistent with a push that never landed, a reviewer's deletion and a network fault, and each wants
a different response. Guessing is how an author is told their work was lost when it was published.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.submission_phase import PreparedSubmission, PushedSubmission
from src.infrastructure.git import (
    enterprise_branch_lifecycle,
    enterprise_sync_state,
    git_work_commits,
    submission_saga,
)
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

CHANGES = ("PCH@1780000001.aaaaaaa.rename",)


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    _, enterprise = build_workflow_pair(tmp_path)
    git(enterprise, "push", "origin", "main")
    return enterprise, tmp_path / "enterprise-origin.git"


def _accumulate(enterprise: Path) -> str:
    branch = enterprise_branch_lifecycle.ensure_working_branch(enterprise)
    write_entity(enterprise, "REQ@1000001301.RecWrk.reconcile-work", "Reconcile Work")
    git_work_commits.commit_enterprise_work(enterprise, "work to submit")
    return branch


def test_nothing_in_flight_is_reported_as_such(pair) -> None:
    enterprise, _ = pair

    outcome = submission_saga.reconcile_submission(enterprise)

    assert outcome.resolved is None
    assert not outcome.advanced
    assert "no submission" in outcome.summary


def test_a_push_that_landed_but_was_never_recorded_is_recovered(pair, monkeypatch) -> None:
    """The window the saga exists for, resolved on the next start rather than by the next attempt."""
    enterprise, origin = pair
    branch = _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)
    real_persist = submission_saga._persist
    monkeypatch.setattr(
        submission_saga,
        "_persist",
        lambda root, phase: (_ for _ in ()).throw(OSError("crash")) if isinstance(phase, PushedSubmission)
        else real_persist(root, phase),
    )
    with pytest.raises(OSError):
        submission_saga.publish_submission(enterprise, prepared)
    monkeypatch.setattr(submission_saga, "_persist", real_persist)
    assert branch in git(origin, "for-each-ref", "refs/heads")

    outcome = submission_saga.reconcile_submission(enterprise)

    assert outcome.advanced
    assert isinstance(outcome.resolved, PushedSubmission)
    assert isinstance(enterprise_sync_state.load(enterprise).submission, PushedSubmission)


def test_a_submission_that_never_published_is_left_retryable(pair) -> None:
    enterprise, _ = pair
    _accumulate(enterprise)
    submission_saga.prepare_submission(enterprise, CHANGES)

    outcome = submission_saga.reconcile_submission(enterprise)

    assert not outcome.advanced
    assert isinstance(outcome.resolved, PreparedSubmission)
    assert "never published" in outcome.summary


def test_a_branch_at_an_unexpected_commit_is_not_resolved_either_way(pair) -> None:
    """Fails closed: the branch moved for a reason this process did not cause."""
    enterprise, _ = pair
    branch = _accumulate(enterprise)
    submission_saga.prepare_submission(enterprise, CHANGES)
    git(enterprise, "push", "origin", f"HEAD~1:refs/heads/{branch}")

    outcome = submission_saga.reconcile_submission(enterprise)

    assert not outcome.advanced
    assert isinstance(outcome.resolved, PreparedSubmission)
    assert "by hand" in outcome.summary


def test_an_unreachable_remote_changes_nothing(pair, monkeypatch) -> None:
    enterprise, _ = pair
    _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)

    def unreachable(*_a, **_k):
        raise RuntimeError("Could not inspect origin for branch 'x'")

    monkeypatch.setattr(submission_saga, "remote_ref_commit", unreachable)
    outcome = submission_saga.reconcile_submission(enterprise)

    assert not outcome.advanced
    assert outcome.resolved == prepared
    assert "cannot reach the remote" in outcome.summary
    assert enterprise_sync_state.load(enterprise).submission == prepared


def test_an_already_published_submission_is_reported_not_re_pushed(pair) -> None:
    enterprise, _ = pair
    _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)
    submission_saga.publish_submission(enterprise, prepared)

    outcome = submission_saga.reconcile_submission(enterprise)

    assert not outcome.advanced
    assert isinstance(outcome.resolved, PushedSubmission)
    assert "awaiting" in outcome.summary


def test_a_completed_submission_is_left_settled(pair) -> None:
    """Reconciling one would re-decide a settled question against a remote that has moved on."""
    enterprise, _ = pair
    _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)
    pushed = submission_saga.publish_submission(enterprise, prepared)
    completed = enterprise_sync_state.load(enterprise).submission.submitted(at="2026-09-03T12:00:00Z")
    enterprise_sync_state.replace_submission(enterprise, completed, status="pending")

    outcome = submission_saga.reconcile_submission(enterprise)

    assert not outcome.advanced
    assert outcome.resolved == completed
    assert "already complete" in outcome.summary
    assert pushed.branch  # the fixture actually published something


def test_reconciliation_is_repeatable(pair) -> None:
    """It runs on every start, so a second pass must reach the same conclusion."""
    enterprise, _ = pair
    _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)
    submission_saga.publish_submission(enterprise, prepared)

    first = submission_saga.reconcile_submission(enterprise)
    second = submission_saga.reconcile_submission(enterprise)

    assert (first.advanced, second.advanced) == (False, False)
    assert first.resolved == second.resolved
