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
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.change_submission import (
    SubmissionUnavailable,
    submit_changes,
)
from src.infrastructure.write.artifact_write.entity_edit import edit_entity
from tests.support.git_workflow_fixtures import ENT_ENTITY_ID, build_workflow_pair, git


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    """An engagement holding one recorded change against a promoted enterprise requirement."""
    engagement, enterprise = build_workflow_pair(tmp_path)
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


def _record_a_change(engagement: Path, repo: ArtifactRepository, summary: str) -> str:
    """Edit the promoted artifact the way an author does, which records a change."""
    registry, verifier = _deps(repo)
    result = edit_entity(
        repo_root=engagement, registry=registry, verifier=verifier,
        clear_repo_caches=lambda _p: repo.refresh(), artifact_id=ENT_ENTITY_ID, repo=repo,
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

    def test_a_change_the_artifact_already_carries_submits_nothing(self, workspace) -> None:
        """Replaying it alters nothing, so there is nothing to put in front of a reviewer — and the
        author is told that rather than shown an empty branch."""
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")
        _submit(engagement, enterprise, repo, change_id)
        second = _record_a_change(engagement, repo, "A further wording")
        # Make the enterprise artifact already say what the second change asks for.
        promoted = enterprise / "model" / "motivation" / "requirement" / f"{ENT_ENTITY_ID}.md"
        promoted.write_text(
            promoted.read_text(encoding="utf-8").replace(
                "Wording the engagement proposes", "A further wording"
            ),
            encoding="utf-8",
        )
        git(enterprise, "add", "-A")
        git(enterprise, "commit", "-m", "a reviewer's own edit")

        with pytest.raises(SubmissionUnavailable, match="altered nothing"):
            _submit(engagement, enterprise, repo, second)

    def test_nothing_is_marked_when_the_set_is_refused(self, workspace) -> None:
        engagement, enterprise, repo = workspace
        change_id = _record_a_change(engagement, repo, "Wording the engagement proposes")

        with pytest.raises(UnsubmittableSet):
            _submit(engagement, enterprise, repo, change_id, "PCH@9.zzzzzzz.gone")

        assert _state_of(repo, change_id) == "draft"
        assert not pending_proposals(
            repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
        ).get("nothing", ())
