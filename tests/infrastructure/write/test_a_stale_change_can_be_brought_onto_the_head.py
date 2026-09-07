"""Rebasing a change: the remedy for the state a change spends most of its life in.

The enterprise branch moves while changes wait, so staleness is the steady state of anything
unreviewed — not an edge case. Reporting it without a remedy left an author no move except to redo
the work, which is why this is an operation.

The rehearsal happens in a throwaway worktree and the replay is a real write judged by the real
verifier, so what these assert is the whole path: git, index, write, verifier, and the restamp.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.enterprise_reference import GLOBAL_ARTIFACT_ID, GLOBAL_ARTIFACT_KIND
from src.application.modeling.proposal_standing import pending_proposals, standing_reader
from src.application.modeling.proposed_change import BASE_REVISION, PROPOSED_CHANGE_TYPE
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.baseline_standing import Proposed
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.change_rebase_op import (
    RebaseUnavailable,
    rebase_changes,
)
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

TARGET = "REQ@1712870400.rrrrrrr.a-promoted-requirement"
REFERENCE = "GAR@1780000060.rrrrrrr.a-promoted-requirement"


def _entity_md(summary: str) -> str:
    return (
        f"---\nartifact-id: {TARGET}\nartifact-type: requirement\nname: A promoted requirement\n"
        "version: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n"
        f"## A promoted requirement\n\n{summary}\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n<!-- §display -->\n"
    )


def _reference_md() -> str:
    return (
        f"---\nartifact-id: {REFERENCE}\nartifact-type: global-artifact-reference\n"
        "name: A promoted requirement\nversion: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n"
        f"{GLOBAL_ARTIFACT_ID}: {TARGET}\n{GLOBAL_ARTIFACT_KIND}: entity\n"
        "global-artifact-entity-type: requirement\n---\n\n<!-- §content -->\n\n"
        "## A promoted requirement\n\nA proxy.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n<!-- §display -->\n"
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root, check=True, capture_output=True,
    )


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    """Both tiers, with the enterprise side a real git repository — the rehearsal needs a worktree."""
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").write_text(
        _entity_md("The enterprise wording."), encoding="utf-8"
    )
    _git(enterprise, "init", "-q")
    _git(enterprise, "add", "-A")
    _git(enterprise, "commit", "-qm", "the enterprise as it was")

    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    (root / "model" / "common" / "global-artifact-reference" / f"{REFERENCE}.md").write_text(
        _reference_md(), encoding="utf-8"
    )
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    return root, enterprise, ArtifactRepository(index)


def _record_a_change(workspace, **fields) -> str:  # noqa: ANN001, ANN003
    root, _enterprise, repo = workspace
    edit_entity(
        repo_root=root,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=REFERENCE, repo=repo, dry_run=False, **fields,
    )
    repo.refresh()
    (change,) = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))[TARGET]
    return change.proposal_id


def _move_upstream(enterprise: Path, summary: str) -> None:
    (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").write_text(
        _entity_md(summary), encoding="utf-8"
    )
    _git(enterprise, "add", "-A")
    _git(enterprise, "commit", "-qm", "upstream moved while the change waited")


def _pending(repo):  # noqa: ANN001, ANN202
    repo.refresh()
    return pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))[TARGET]


# ── the clean case, which is the point of the operation ──────────────────────


def test_a_stale_change_that_still_applies_is_reported_clean(workspace) -> None:  # noqa: ANN001
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "Someone else's wording.")

    report = rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    (classified,) = report.rehearsed.changes
    assert classified.outcome == "clean"


def test_a_clean_rebase_restamps_the_revision_it_was_proven_against(workspace) -> None:  # noqa: ANN001
    """The remedy itself: afterwards the change is no longer stale."""
    _root, enterprise, repo = workspace
    change_id = _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "Someone else's wording.")
    assert _stale(repo)

    report = rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    assert report.restamped == (change_id,)
    assert not _stale(repo)


def test_the_recorded_edit_itself_is_untouched(workspace) -> None:  # noqa: ANN001
    """A rebase records what the change was proven against; the fields are the author's intent, and
    the intent is what re-applied."""
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "Someone else's wording.")

    rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    (change,) = _pending(repo)
    assert change.edit.fields == {"summary": "My wording."}


def test_the_enterprise_checkout_is_left_as_it_was(workspace) -> None:  # noqa: ANN001
    """The replay is a real write, made somewhere disposable."""
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "Someone else's wording.")
    before = (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").read_text(
        encoding="utf-8"
    )

    rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    assert (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").read_text(
        encoding="utf-8"
    ) == before


# ── the other two outcomes ───────────────────────────────────────────────────


def test_a_change_the_artifact_already_carries_is_superseded_not_conflicting(workspace) -> None:  # noqa: ANN001
    """Reporting this as a conflict would ask an author to resolve their own accepted work."""
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "My wording.")

    report = rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    (classified,) = report.rehearsed.changes
    assert classified.outcome == "superseded"


def test_a_superseded_change_is_reported_and_not_acted_on(workspace) -> None:  # noqa: ANN001
    """Closing it here would be this operation deciding a coincidence is an integration — the
    judgement the sweep deliberately reserves for changes that were actually submitted."""
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    _move_upstream(enterprise, "My wording.")

    report = rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    assert report.restamped == ()
    assert len(_pending(repo)) == 1


def test_a_target_that_is_gone_conflicts_rather_than_crashing(workspace) -> None:  # noqa: ANN001
    _root, enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")
    (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").unlink()
    _git(enterprise, "add", "-A")
    _git(enterprise, "commit", "-qm", "the artifact was removed upstream")

    report = rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    (classified,) = report.rehearsed.changes
    assert classified.outcome == "conflicting"
    assert "nothing to apply to" in classified.reason


# ── where a rebase cannot be attempted at all ────────────────────────────────


def test_a_deployment_without_the_enterprise_repository_is_told_why(workspace) -> None:  # noqa: ANN001
    """Refused rather than reported as a conflict, which would blame the change for the
    deployment's shape."""
    _root, _enterprise, repo = workspace
    _record_a_change(workspace, summary="My wording.")

    with pytest.raises(RebaseUnavailable, match="both repositories are mounted"):
        rebase_changes(_pending(repo), enterprise_root=None, repo=repo)


def test_nothing_pending_is_not_an_error(workspace) -> None:  # noqa: ANN001
    _root, enterprise, repo = workspace

    report = rebase_changes((), enterprise_root=enterprise, repo=repo)

    assert report.rehearsed.changes == ()


def _stale(repo) -> bool:  # noqa: ANN001
    repo.refresh()
    standing = standing_reader(repo)(TARGET)
    return isinstance(standing, Proposed) and standing.condition == "stale"


def test_the_base_revision_on_disk_is_what_moved(workspace) -> None:  # noqa: ANN001
    """Stated over the file, because the standing is derived and could agree for another reason."""
    _root, enterprise, repo = workspace
    change_id = _record_a_change(workspace, summary="My wording.")
    before = parse_frontmatter(repo.get_entity(change_id).path.read_text(encoding="utf-8"))
    _move_upstream(enterprise, "Someone else's wording.")

    rebase_changes(_pending(repo), enterprise_root=enterprise, repo=repo)

    after = parse_frontmatter(repo.get_entity(change_id).path.read_text(encoding="utf-8"))
    assert after[BASE_REVISION] != before[BASE_REVISION]
