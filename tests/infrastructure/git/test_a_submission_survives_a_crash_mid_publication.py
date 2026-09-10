"""Publishing a submission converges on one review branch, whatever fails and whenever.

The push updates a shared remote nothing local can roll back, and the local write happens afterwards.
So there is a window in which the branch is published and nothing local knows it. The saga closes
that window by recording the intent first and *deriving* the outcome from the remote ref afterwards
— never from the fact that a push call returned.

One test per boundary the plan names:

* failure before the push leaves nothing marked and no remote branch,
* failure after the remote updates but before local persistence converges on retry to **one** branch
  and one truthful status,
* a remote ref at an unexpected commit **fails closed** rather than passing as an idempotent retry,
* and a branch that already exists elsewhere is never overwritten.

Real git repositories with a real bare origin throughout: the whole subject is what the remote says,
and a fake would be asserting the thing under test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.domain.submission_phase import PreparedSubmission, PushedSubmission
from src.infrastructure.git import (
    enterprise_branch_lifecycle,
    enterprise_sync_state,
    git_work_commits,
    submission_saga,
)
from src.infrastructure.git.submission_saga import SubmissionConflict
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

CHANGES = ("PCH@1780000001.aaaaaaa.rename", "PCH@1780000002.bbbbbbb.restate")


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    _, enterprise = build_workflow_pair(tmp_path)
    git(enterprise, "push", "origin", "main")
    return enterprise, tmp_path / "enterprise-origin.git"


def _accumulate(enterprise: Path) -> str:
    branch = enterprise_branch_lifecycle.ensure_working_branch(enterprise)
    write_entity(enterprise, "REQ@1000001201.SubWrk.submission-work", "Submission Work")
    git_work_commits.commit_enterprise_work(enterprise, "work to submit")
    return branch


def _remote_heads(origin: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(origin), "for-each-ref", "refs/heads"], check=True, capture_output=True, text=True
    ).stdout


def _branches_on(origin: Path) -> list[str]:
    return [line.split("refs/heads/")[-1] for line in _remote_heads(origin).splitlines() if "refs/heads/" in line]


class TestTheOrdinaryPublication:
    def test_it_records_the_intent_before_touching_the_remote(self, pair) -> None:
        enterprise, origin = pair
        branch = _accumulate(enterprise)

        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        assert branch not in _remote_heads(origin), "prepare must not push"
        stored = enterprise_sync_state.load(enterprise).submission
        assert isinstance(stored, PreparedSubmission)
        assert stored.intent.proposal_ids == CHANGES
        assert stored.intent.expected_commit == prepared.intent.expected_commit

    def test_publishing_pushes_the_branch_and_marks_it_pushed(self, pair) -> None:
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        outcome = submission_saga.publish_submission(enterprise, prepared)

        assert outcome.pushed_now
        assert outcome.branch == branch
        assert branch in _remote_heads(origin)
        assert isinstance(enterprise_sync_state.load(enterprise).submission, PushedSubmission)

    def test_the_expected_commit_is_the_one_that_lands(self, pair) -> None:
        enterprise, origin = pair
        _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        outcome = submission_saga.publish_submission(enterprise, prepared)
        landed = git(origin, "rev-parse", f"refs/heads/{outcome.branch}")

        assert landed == prepared.intent.expected_commit


class TestFailureBeforeThePush:
    def test_nothing_is_marked_and_no_branch_is_published(self, pair, monkeypatch) -> None:
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        def failing_push(repo, *args, **kwargs):
            if args[:1] == ("push",):
                return (1, "", "injected push failure")
            return real(repo, *args, **kwargs)

        real = submission_saga.run_repo_git
        monkeypatch.setattr(submission_saga, "run_repo_git", failing_push)
        with pytest.raises(RuntimeError, match="Failed to push"):
            submission_saga.publish_submission(enterprise, prepared)

        assert branch not in _remote_heads(origin)
        # Still `prepared`: the record is the evidence a retry needs, so it must survive the failure.
        assert isinstance(enterprise_sync_state.load(enterprise).submission, PreparedSubmission)


class TestFailureAfterTheRemoteUpdates:
    def test_a_retry_converges_on_one_branch_and_one_truthful_status(self, pair, monkeypatch) -> None:
        """The window the saga exists for: the push lands, the process dies before persisting."""
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        def die_after_pushing(root, phase):
            if isinstance(phase, PushedSubmission):
                raise OSError("injected crash before persisting")
            return real_persist(root, phase)

        real_persist = submission_saga._persist
        monkeypatch.setattr(submission_saga, "_persist", die_after_pushing)
        with pytest.raises(OSError):
            submission_saga.publish_submission(enterprise, prepared)

        assert branch in _remote_heads(origin), "the push did land"
        assert isinstance(enterprise_sync_state.load(enterprise).submission, PreparedSubmission)

        monkeypatch.setattr(submission_saga, "_persist", real_persist)
        outcome = submission_saga.publish_submission(enterprise, prepared)

        assert not outcome.pushed_now, "the retry recognised its own completed push"
        assert _branches_on(origin).count(branch) == 1
        assert isinstance(enterprise_sync_state.load(enterprise).submission, PushedSubmission)

    def test_the_retry_is_repeatable(self, pair) -> None:
        """Converging once is not enough: reconciliation may run on every startup."""
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)

        first = submission_saga.publish_submission(enterprise, prepared)
        second = submission_saga.publish_submission(enterprise, prepared)
        third = submission_saga.publish_submission(enterprise, prepared)

        assert (first.pushed_now, second.pushed_now, third.pushed_now) == (True, False, False)
        assert _branches_on(origin).count(branch) == 1


def _publish_someone_elses_commit(enterprise: Path, branch: str) -> None:
    """Put a commit on `origin/<branch>` that the local branch does not descend from."""
    git(enterprise, "checkout", "-b", "another-workspace", "HEAD~1")
    write_entity(enterprise, "REQ@1000001202.Theirs.someone-elses-work", "Someone Else's Work")
    git_work_commits.commit_enterprise_work(enterprise, "someone else's work")
    git(enterprise, "push", "origin", f"HEAD:refs/heads/{branch}")
    git(enterprise, "checkout", branch)


class TestASecondSubmissionOntoTheSameBranch:
    """Successive changes accumulate on one working branch, so this is the ordinary case.

    The remote is then exactly where the first submission left it, and the difference between that
    and someone else's move is reachability, not inequality. Refusing it made a second submission
    impossible — which nothing noticed while the saga had no production caller.
    """

    def test_it_fast_forwards_the_branch_it_already_published(self, pair) -> None:
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        submission_saga.publish_submission(
            enterprise, submission_saga.prepare_submission(enterprise, CHANGES)
        )
        write_entity(enterprise, "REQ@1000001203.More.further-work", "Further Work")
        git_work_commits.commit_enterprise_work(enterprise, "more work to submit")

        outcome = submission_saga.publish_submission(
            enterprise, submission_saga.prepare_submission(enterprise, CHANGES)
        )

        assert outcome.pushed_now
        assert git(origin, "rev-parse", f"refs/heads/{branch}") == outcome.commit
        assert _branches_on(origin).count(branch) == 1


class TestARefAtAnUnexpectedCommitFailsClosed:
    def test_a_branch_already_on_origin_at_another_commit_is_not_overwritten(self, pair) -> None:
        """Someone else moved it — a reviewer's amend, a force-push, another workspace."""
        enterprise, origin = pair
        branch = _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)
        # A commit this branch does not descend from, which is what "someone else moved it" means.
        # It used to publish `HEAD~1`, an *ancestor* — indistinguishable from this repository's own
        # earlier publication, which is the ordinary second submission onto an accumulating branch.
        _publish_someone_elses_commit(enterprise, branch)
        theirs = git(origin, "rev-parse", f"refs/heads/{branch}")

        with pytest.raises(SubmissionConflict, match="Someone else has moved it"):
            submission_saga.publish_submission(enterprise, prepared)

        assert git(origin, "rev-parse", f"refs/heads/{branch}") == theirs, "their commit stands"
        assert isinstance(enterprise_sync_state.load(enterprise).submission, PreparedSubmission)

    def test_a_ref_that_moves_between_the_push_and_the_confirmation_is_reported(
        self, pair, monkeypatch
    ) -> None:
        """The narrow race: confirmation reads the ref back, and must not accept any answer."""
        enterprise, _origin = pair
        _accumulate(enterprise)
        prepared = submission_saga.prepare_submission(enterprise, CHANGES)
        answers = iter([None, "0000000000000000000000000000000000000000"])
        monkeypatch.setattr(submission_saga, "remote_ref_commit", lambda *_a, **_k: next(answers))
        monkeypatch.setattr(submission_saga, "run_repo_git", lambda *_a, **_k: (0, "", ""))

        with pytest.raises(SubmissionConflict, match="not the"):
            submission_saga.publish_submission(enterprise, prepared)

        assert isinstance(enterprise_sync_state.load(enterprise).submission, PreparedSubmission)


def test_a_submission_is_never_marked_pushed_without_the_remote_agreeing(pair, monkeypatch) -> None:
    """The invariant behind all of the above, stated once: the ref decides, not the push call."""
    enterprise, _origin = pair
    _accumulate(enterprise)
    prepared = submission_saga.prepare_submission(enterprise, CHANGES)
    monkeypatch.setattr(submission_saga, "run_repo_git", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(submission_saga, "remote_ref_commit", lambda *_a, **_k: None)

    with pytest.raises(SubmissionConflict):
        submission_saga.publish_submission(enterprise, prepared)

    assert isinstance(enterprise_sync_state.load(enterprise).submission, PreparedSubmission)
