"""Submitting recorded changes: the step that makes them anybody's but the author's.

Everything before this is local by design — a change is a semantic edit held in the engagement
repository, and nothing upstream knows it exists. Submitting replays those edits into the enterprise
repository, commits and publishes the result, and only then marks the changes. So the tests are about
what is true *after* each of those steps, and about the states in which none of them happens.

Real git repositories with a real bare origin, because the whole subject is what the remote carries
and what the enterprise checkout now says. A fake would be asserting the thing under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.application.modeling.submission_set import UnsubmittableSet
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.submission_phase import CompletedSubmission, PushedSubmission
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.enterprise_branch_lifecycle import ensure_working_branch
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.change_rebase_op import RebaseUnavailable
from src.infrastructure.write.artifact_write.change_submission import (
    SubmissionUnavailable,
    complete_submission,
    submit_changes,
)
from src.infrastructure.write.artifact_write.entity_edit import edit_entity
from src.infrastructure.write.artifact_write.integration_cleanup import close_integrated_changes
from src.infrastructure.write.artifact_write.proposal_lifecycle import (
    DiscardRefused,
    discard_change,
    mark_proposal_state,
)
from tests.support.git_workflow_fixtures import (
    ENT_ENTITY_ID,
    build_workflow_pair,
    git,
    valid_entity_md,
)

#: A second promoted artifact, so a submission can carry a set rather than one change.
OTHER_ID = "REQ@1000000605.WfTwo.a-second-enterprise-requirement"
#: Something promoted onto the working branch that is not a change and has its own review.
PROMOTED_ID = "REQ@1000000604.Prom.newly-promoted"


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    """An engagement holding one recorded change against a promoted enterprise requirement."""
    engagement, enterprise = build_workflow_pair(tmp_path)
    (enterprise / "model" / "motivation" / "requirement" / f"{OTHER_ID}.md").write_text(
        valid_entity_md(OTHER_ID, "A Second Enterprise Requirement"), encoding="utf-8"
    )
    git(enterprise, "add", "model")
    git(enterprise, "commit", "-m", "a second promoted artifact")
    git(enterprise, "push", "origin", "main")
    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    repo = ArtifactRepository(index)
    try:
        yield engagement, enterprise, repo
    finally:
        index.close()


def _deps(repo: ArtifactRepository):  # noqa: ANN202
    registry = ArtifactRegistry(repo._store)  # noqa: SLF001 — the write path is handed one
    return registry, build_artifact_verifier(registry, catalogs=process_runtime_catalogs())


def _record_a_change(
    engagement: Path, repo: ArtifactRepository, summary: str, *, target: str = ENT_ENTITY_ID
) -> str:
    """Edit the promoted artifact the way an author does, which records a change."""
    registry, verifier = _deps(repo)
    result = edit_entity(
        repo_root=engagement, registry=registry, verifier=verifier,
        clear_repo_caches=lambda _p: repo.refresh(), artifact_id=target, repo=repo,
        dry_run=False, summary=summary,
    )
    repo.refresh()
    assert result.artifact_id is not None
    return result.artifact_id


def _submit(engagement: Path, enterprise: Path, repo: ArtifactRepository, *ids: str):  # noqa: ANN202
    registry, verifier = _deps(repo)
    return submit_changes(
        ids, repo=repo, enterprise_root=enterprise, registry=registry, verifier=verifier,
        clear_repo_caches=lambda _p: repo.refresh(),
    )


def _state_of(repo: ArtifactRepository, change_id: str) -> str:
    repo.refresh()
    record = repo.get_entity(change_id)
    assert record is not None
    return str(record.extra.get("proposal-state", ""))


class TestTheOrdinarySubmission:
    def test_the_enterprise_artifact_carries_the_change_afterwards(self, workspace) -> None:
        """The replay is the write call. Until this happens, nothing upstream has the edit at all."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        _submit(engagement, enterprise, repo, change_id)

        promoted = (enterprise / "model" / "motivation" / "requirement" / f"{ENT_ENTITY_ID}.md")
        assert "Wording the engagement proposes" in promoted.read_text(encoding="utf-8")

    def test_the_branch_reaches_the_remote(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        report = _submit(engagement, enterprise, repo, change_id)

        assert report.pushed_now
        assert report.branch in git(enterprise, "ls-remote", "--heads", "origin")

    def test_the_change_is_marked_submitted(self, workspace) -> None:
        """Not before: the marking is what tells the author someone can see it, and the remote is
        what decides whether anyone can."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        assert _state_of(repo, change_id) == "draft"

        _submit(engagement, enterprise, repo, change_id)

        assert _state_of(repo, change_id) == "submitted"

    def test_a_just_submitted_change_does_not_read_as_stale(self, workspace) -> None:
        """The replay moves the enterprise artifact — by this change's own hand. Reading that as
        staleness would send an author to rebase the thing they have just submitted, and would churn
        a review branch per submission."""
        from src.application.modeling.change_overview import recorded_changes  # noqa: PLC0415

        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        _submit(engagement, enterprise, repo, change_id)
        repo.refresh()

        (row,) = [c for c in recorded_changes(repo) if c.change_id == change_id]
        assert row.condition == "current"

    def test_the_branch_stops_accumulating(self, workspace) -> None:
        """The regional invariant: no change reads `submitted` while its branch is `accumulating`."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        _submit(engagement, enterprise, repo, change_id)

        assert enterprise_sync_state.load(enterprise).status == "pending"


class TestWhenItMustNotHappen:
    def test_a_deployment_with_no_enterprise_repository_is_told_why(self, workspace) -> None:
        engagement, _enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        registry, verifier = _deps(repo)

        with pytest.raises(SubmissionUnavailable, match="no enterprise repository"):
            submit_changes(
                (change_id,), repo=repo, enterprise_root=None, registry=registry,
                verifier=verifier, clear_repo_caches=lambda _p: None,
            )

    def test_unsaved_enterprise_work_is_not_swept_into_the_submission(self, workspace) -> None:
        """The commit stages the whole tree, so an unsaved admin edit would be published as though
        the engagement had proposed it."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        (enterprise / "docs").mkdir(exist_ok=True)
        (enterprise / "docs" / "unsaved.md").write_text("someone's work in progress\n", encoding="utf-8")

        with pytest.raises(SubmissionUnavailable, match="unsaved changes"):
            _submit(engagement, enterprise, repo, change_id)

        assert _state_of(repo, change_id) == "draft"

    def test_a_change_upstream_already_carries_is_refused(self, workspace) -> None:
        """There is nothing to put in front of a reviewer, and replaying it is not harmless: the
        write path stamps `last-updated`, so it would publish a commit that moves a timestamp and
        nothing else. Decided by content before the replay, not inferred from the diff after it —
        and against upstream, because this checkout carries our own unpublished work."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _upstream_already_says(enterprise, "Wording the engagement proposes")
        repo.refresh()

        with pytest.raises(SubmissionUnavailable, match="Upstream already says"):
            _submit(engagement, enterprise, repo, change_id)

        assert _state_of(repo, change_id) == "draft"

    def test_nothing_is_marked_when_the_set_is_refused(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        with pytest.raises(UnsubmittableSet):
            _submit(engagement, enterprise, repo, change_id, "PCH@9.zzzzzzz.gone")

        assert _state_of(repo, change_id) == "draft"
        assert not pending_proposals(
            repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
        ).get("nothing", ())


class TestASubmissionLeftUnmarked:
    """The window the saga exists for: the push landed and the process died before the marking.

    `reconcile_submission` resolves the remote half at startup and can go no further — it runs
    before the repository exists. It leaves a `pushed` record, and finishing that record is what
    stops a branch a reviewer can already see carrying changes this repository still calls drafts.
    """

    def test_an_ordinary_submission_leaves_nothing_to_reconcile(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        _submit(engagement, enterprise, repo, change_id)

        assert isinstance(enterprise_sync_state.load(enterprise).submission, CompletedSubmission)

    def test_a_pushed_submission_is_finished(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        _rewind_to_pushed(enterprise, repo, change_id)
        assert _state_of(repo, change_id) == "draft"

        marked = complete_submission(repo=repo, enterprise_root=enterprise)

        assert marked == (change_id,)
        assert _state_of(repo, change_id) == "submitted"
        assert isinstance(enterprise_sync_state.load(enterprise).submission, CompletedSubmission)

    def test_a_start_with_no_submission_in_flight_does_nothing(self, workspace) -> None:
        """The ordinary case at startup, and it must not be an error or a warning."""
        _engagement, enterprise, repo = workspace

        assert complete_submission(repo=repo, enterprise_root=enterprise) == ()


def _rewind_to_pushed(enterprise: Path, repo: ArtifactRepository, change_id: str) -> None:
    """The state a process leaves by dying between the push and the marking."""
    completed = enterprise_sync_state.load(enterprise).submission
    assert isinstance(completed, CompletedSubmission)
    enterprise_sync_state.replace_submission(
        enterprise,
        PushedSubmission(intent=completed.intent, pushed_at=completed.pushed_at),
        status=enterprise_sync_state.load(enterprise).status,
    )
    record = repo.get_entity(change_id)
    assert record is not None
    mark_proposal_state(record.path, artifact_id=change_id, state="draft")
    repo.refresh()


class TestRebasingASetAlreadyUnderReview:
    """D4b: the branch is the unit of review, so a rebase replaces it rather than rewriting it.

    Force-pushing would change the commits underneath a reviewer with nothing to say so. Opening a
    branch and *not* publishing it would leave the changes reading `submitted` while their branch is
    `accumulating`, which is the one pairing of the two lifecycles the regional invariant forbids.
    So the replacement is opened, replayed onto, published, and only then is the old one retired.
    """

    def test_it_publishes_a_replacement_and_retires_the_reviewed_branch(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        first = _submit(engagement, enterprise, repo, change_id)
        _main_moves_while_the_change_waits(enterprise)

        report = _rebase(repo, enterprise, change_id)

        assert report.republished is not None
        replacement = report.republished.branch
        assert replacement != first.branch
        heads = _remote_heads(enterprise)
        assert replacement in heads
        assert first.branch not in heads, "the branch it replaced is retired once the successor is up"

    def test_the_replacement_carries_the_change_on_top_of_what_moved(self, workspace) -> None:
        """Read off the replacement branch itself, which is the only thing a reviewer sees.

        Both halves matter: the branch must carry the change, or it is a review of nothing, and it
        must carry what moved underneath, or it is the old branch under a new name.
        """
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        _main_moves_while_the_change_waits(enterprise)

        report = _rebase(repo, enterprise, change_id)

        assert report.republished is not None
        published = git(
            enterprise, "show",
            f"{report.republished.branch}:model/motivation/requirement/{ENT_ENTITY_ID}.md",
        )
        assert "Wording the engagement proposes" in published, "the change is on it"
        assert "status: active" in published, "and so is what moved underneath it"

    def test_the_branch_never_rests_in_accumulating(self, workspace) -> None:
        """The regional invariant: a change reading `submitted` on an `accumulating` branch is the
        state in which nothing local can say whether a reviewer is looking at this work or at the
        version it replaced."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        _main_moves_while_the_change_waits(enterprise)

        report = _rebase(repo, enterprise, change_id)

        assert report.republished is not None
        state = enterprise_sync_state.load(enterprise)
        assert state.status == "pending"
        assert state.branch == report.republished.branch, "the recorded branch is the new one"
        assert state.superseded_branch is None, "nothing is left waiting to be retired"
        assert _state_of(repo, change_id) == "submitted", "a rebase does not move the lifecycle"

    def test_a_draft_rebase_publishes_nothing(self, workspace) -> None:
        """There is no branch under review to protect, and opening one would publish work its author
        never submitted."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _main_moves_while_the_change_waits(enterprise)

        report = _rebase(repo, enterprise, change_id)

        assert report.republished is None
        assert not [head for head in _remote_heads(enterprise) if head.startswith("arch/")]


def _remote_heads(enterprise: Path) -> list[str]:
    """The branch names on origin, exactly.

    Names rather than the raw `ls-remote` text: two branches created in the same second differ by a
    numeric suffix, so a substring test finds the retired branch inside the name of the one that
    replaced it and reports a retirement that did happen as one that did not.
    """
    listing = git(enterprise, "ls-remote", "--heads", "origin")
    return [line.split("refs/heads/", 1)[1] for line in listing.splitlines() if "refs/heads/" in line]


def _main_moves_while_the_change_waits(enterprise: Path) -> None:
    """Advance the upstream the review branch will be merged into.

    On `main`, not on the working branch: that is where the enterprise repository's own work lands,
    and it is what a review branch goes stale against. Editing the working branch instead would be
    this repository amending its own submission, which is a different act with a different remedy.
    """
    working = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
    git(enterprise, "checkout", "main")
    promoted = enterprise / "model" / "motivation" / "requirement" / f"{ENT_ENTITY_ID}.md"
    # A modelled field, not free prose in the body: every write in this product re-renders the
    # artifact from the fields it knows, so a paragraph nothing models would not survive the replay
    # and the test would be asserting the renderer's limits rather than where the branch was opened.
    promoted.write_text(
        promoted.read_text(encoding="utf-8").replace("status: draft", "status: active"),
        encoding="utf-8",
    )
    # The model only. `git add -A` here stages `.arch/`, the runtime sync state, onto main — and
    # switching back to the working branch then deletes it, resetting the repository to `synced` and
    # making the submission it was holding disappear. The product excludes that directory from every
    # commit it makes for the same reason.
    git(enterprise, "add", "model")
    git(enterprise, "commit", "-m", "the enterprise repository's own work")
    git(enterprise, "push", "origin", "main")
    git(enterprise, "checkout", working)
    git(enterprise, "fetch", "origin")


def _rebase(repo: ArtifactRepository, enterprise: Path, change_id: str):  # noqa: ANN202
    from src.infrastructure.write.artifact_write.change_rebase_op import rebase_changes

    repo.refresh()
    proposal = next(
        p
        for group in pending_proposals(
            repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
        ).values()
        for p in group
        if p.proposal_id == change_id
    )
    registry, verifier = _deps(repo)
    return rebase_changes(
        (proposal,), enterprise_root=enterprise, repo=repo, registry=registry,
        verifier=verifier, clear_repo_caches=lambda _p: repo.refresh(),
    )


class TestTheSweepAfterASubmission:
    """The sweep judges a change integrated when the enterprise artifact carries its effect.

    Which reference that is decides everything. A submission replays the effect onto *this*
    deployment's working branch, so reading the local checkout made every change read as integrated
    the instant it was submitted — closed terminally, and its review branch deleted from the remote
    while somebody was reading it. Upstream is the only reference under which "the artifact carries
    this" means "somebody took it up".
    """

    def test_a_submitted_change_is_not_closed_by_its_own_replay(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        report = _submit(engagement, enterprise, repo, change_id)
        repo.refresh()  # exactly what startup does before sweeping

        swept = close_integrated_changes(repo)

        assert swept.closed == ()
        assert _state_of(repo, change_id) == "submitted"
        assert report.branch in _remote_heads(enterprise), "the reviewer's branch is still there"

    def test_it_closes_the_change_once_upstream_carries_it(self, workspace) -> None:
        """The sweep still does its job — this is the event it exists for."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        report = _submit(engagement, enterprise, repo, change_id)
        _a_reviewer_merges(enterprise, report.branch)
        repo.refresh()

        swept = close_integrated_changes(repo)

        assert len(swept.closed) == 1
        assert _state_of(repo, change_id) == "integrated"

    def test_nothing_is_closed_when_upstream_cannot_be_read(self, workspace) -> None:
        """Not knowing is not evidence. Absence of a readable upstream is equally consistent with a
        fetch that never ran and a branch somebody deleted, and each wants a different answer."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        git(enterprise, "update-ref", "-d", "refs/remotes/origin/main")
        repo.refresh()

        swept = close_integrated_changes(repo)

        assert swept.closed == ()
        assert _state_of(repo, change_id) == "submitted"

    def test_the_branch_survives_while_it_carries_work_upstream_lacks(self, workspace) -> None:
        """Retiring is deleting a branch from a shared remote. "No change is still pending" is not
        "the branch is finished" — the same branch carries promotions, which are not changes."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        report = _submit(engagement, enterprise, repo, change_id)
        _a_reviewer_merges(enterprise, report.branch)
        _more_work_lands_on_the_branch(enterprise)
        repo.refresh()

        swept = close_integrated_changes(repo)

        assert len(swept.closed) == 1, "the change is integrated"
        assert report.branch in _remote_heads(enterprise), "and the branch is not deleted"


def _a_reviewer_merges(enterprise: Path, branch: str) -> None:
    """What acceptance looks like from here: the branch's content reaches `origin/main`."""
    working = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
    git(enterprise, "checkout", "main")
    git(enterprise, "merge", "--no-ff", branch, "-m", "reviewer merged the submission")
    git(enterprise, "push", "origin", "main")
    git(enterprise, "checkout", working)
    git(enterprise, "fetch", "origin")


def _more_work_lands_on_the_branch(enterprise: Path) -> None:
    """A commit on the review branch that upstream does not have — a promotion stands in."""
    promoted = enterprise / "model" / "motivation" / "requirement" / "REQ@1000000603.Prom.promoted-later.md"
    promoted.write_text(
        valid_entity_md("REQ@1000000603.Prom.promoted-later", "Promoted Later"), encoding="utf-8"
    )
    git(enterprise, "add", "model")
    git(enterprise, "commit", "-m", "a promotion nobody has reviewed yet")


class TestASubmissionInterruptedBeforeItPushed:
    """The window between the commit and the push, which no local rollback can close.

    A previous attempt has already put the replay on the branch; the changes are still `draft`
    because nothing was published for them to be marked against. The retry must converge on the
    commit that exists rather than treat it as evidence that there is nothing to do — read locally,
    it looked exactly like a change the artifact already carried, and the advice was to discard it.
    """

    def test_the_retry_publishes_the_commit_the_first_attempt_left(self, workspace, monkeypatch) -> None:  # noqa: ANN001
        from src.infrastructure.write.artifact_write import change_submission

        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        def _died(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            raise RuntimeError("the process died between the commit and the push")

        monkeypatch.setattr(change_submission, "publish_submission", _died)
        with pytest.raises(RuntimeError, match="died between"):
            _submit(engagement, enterprise, repo, change_id)
        monkeypatch.undo()
        assert _state_of(repo, change_id) == "draft", "nothing was marked"

        report = _submit(engagement, enterprise, repo, change_id)

        assert _state_of(repo, change_id) == "submitted"
        assert report.branch in _remote_heads(enterprise)


class TestAChangeWhoseBranchWentAway:
    """A reviewer merged some of the set and not others, or deleted the branch without merging.

    D6's transition, and the only one that lets an author recover: the change is not rejected — no
    such state exists in v0.9.0 — and it is not integrated. It is simply not in front of anybody,
    and leaving it `submitted` against a branch that no longer exists is a state nothing can act on.
    """

    def test_it_returns_to_draft_when_no_branch_is_published(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        report = _submit(engagement, enterprise, repo, change_id)
        _the_branch_goes_away_unmerged(enterprise, report.branch)
        repo.refresh()

        swept = close_integrated_changes(repo)

        assert swept.returned_to_draft == (change_id,)
        assert _state_of(repo, change_id) == "draft", "the author can revise it or send it again"

    def test_it_stays_submitted_while_its_branch_is_published(self, workspace) -> None:
        """The ordinary case, and the one this must not touch: under review is not stranded."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        repo.refresh()

        swept = close_integrated_changes(repo)

        assert swept.returned_to_draft == ()
        assert _state_of(repo, change_id) == "submitted"


def _the_branch_goes_away_unmerged(enterprise: Path, branch: str) -> None:
    """A reviewer closes the review without merging: the branch goes, upstream never carried it."""
    git(enterprise, "checkout", "main")
    git(enterprise, "push", "origin", "--delete", branch)
    git(enterprise, "branch", "-D", branch)
    from src.infrastructure.git import enterprise_sync_state

    enterprise_sync_state.clear_lifecycle(enterprise)


class TestRebasingABranchThatCarriesMore:
    """A replacement is built from upstream plus the set, and the branch it replaces is deleted.

    So anything else the old branch held has to be accounted for, or it exists nowhere afterwards.
    A promotion sharing the review branch was destroyed that way — measured: present on the old
    branch, absent from upstream, absent from the replacement, and the old branch retired.
    """

    def test_a_promotion_sharing_the_branch_refuses_the_rebase(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        ensure_working_branch(enterprise)
        _a_promotion_lands_on_the_branch(enterprise)
        report = _submit(engagement, enterprise, repo, change_id)
        _main_moves_while_the_change_waits(enterprise)

        with pytest.raises(RebaseUnavailable, match="do not account for"):
            _rebase(repo, enterprise, change_id)

        assert report.branch in _remote_heads(enterprise), "and the branch it would have deleted stands"
        assert "newly-promoted" in git(enterprise, "ls-tree", "-r", "--name-only", report.branch)

    def test_the_whole_submitted_set_is_replayed_not_the_one_asked_about(self, workspace) -> None:
        """Replaying a subset onto a fresh branch would drop the rest of the set from the very
        branch that exists to carry it."""
        engagement, enterprise, repo = workspace
        first = _record_a_change(engagement, repo, "Wording the engagement proposes")
        second = _record_a_change(engagement, repo, "A second artifact's wording", target=OTHER_ID)
        _submit(engagement, enterprise, repo, first, second)
        _main_moves_while_the_change_waits(enterprise)

        report = _rebase(repo, enterprise, first)

        assert report.republished is not None
        assert {c.proposal_id for c in report.rehearsed.changes} == {first, second}
        published = git(
            enterprise, "show",
            f"{report.republished.branch}:model/motivation/requirement/{OTHER_ID}.md",
        )
        assert "A second artifact's wording" in published, "the other change is on the replacement"


class TestTakingBackASubmittedChange:
    """Marking a change `abandoned` does not take its effect off the branch carrying it.

    So the record would say withdrawn while the branch still offered the work for merging — and a
    later rebase could not repair it, because the withdrawn change's effect is then work the live
    set does not account for, which refuses the rebase outright.
    """

    def test_it_is_refused_while_its_branch_is_published(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        repo.refresh()

        with pytest.raises(DiscardRefused, match="published for review"):
            discard_change(repo, artifact_id=change_id, enterprise_root=enterprise)

        assert _state_of(repo, change_id) == "submitted"

    def test_withdrawing_the_submission_makes_it_ordinary_again(self, workspace) -> None:
        """The remedy composes out of what already exists: the branch goes, the change returns to
        draft, and taking it back is a local act again."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        report = _submit(engagement, enterprise, repo, change_id)
        _the_branch_goes_away_unmerged(enterprise, report.branch)
        repo.refresh()
        close_integrated_changes(repo)

        _path, discarded = discard_change(repo, artifact_id=change_id, enterprise_root=enterprise)

        assert discarded
        assert _state_of(repo, change_id) == "abandoned"

    def test_a_draft_is_taken_back_without_ceremony(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        _path, discarded = discard_change(repo, artifact_id=change_id, enterprise_root=enterprise)

        assert discarded
        assert _state_of(repo, change_id) == "abandoned"


def _a_promotion_lands_on_the_branch(enterprise: Path) -> None:
    """Promoted content is committed on the same working branch a submission publishes."""
    promoted = enterprise / "model" / "motivation" / "requirement" / f"{PROMOTED_ID}.md"
    promoted.write_text(valid_entity_md(PROMOTED_ID, "Newly Promoted"), encoding="utf-8")
    git(enterprise, "add", "model")
    git(enterprise, "commit", "-m", "a promotion nobody has reviewed yet")


def _upstream_already_says(enterprise: Path, summary: str) -> None:
    """Put the change's own wording on `origin/main`, without this checkout carrying it."""
    working = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
    git(enterprise, "checkout", "main")
    promoted = enterprise / "model" / "motivation" / "requirement" / f"{ENT_ENTITY_ID}.md"
    promoted.write_text(
        promoted.read_text(encoding="utf-8").replace("Workflow fixture.", summary), encoding="utf-8"
    )
    git(enterprise, "add", "model")
    git(enterprise, "commit", "-m", "upstream arrives at the same wording")
    git(enterprise, "push", "origin", "main")
    git(enterprise, "checkout", working)
    git(enterprise, "fetch", "origin")
