"""Editing enterprise-owned content records a change instead of corrupting its reference.

An engagement repository holds a *reference* to a promoted artifact, not the artifact. Writing the
fields there edits the reference — dropping the field that names what it stands for, and failing
verification with `E140`, a message about a symptom of the write path's own write rather than about
what the author did. The first test here is that hole, stated as the behaviour that replaces it.

The whole point is that the author does nothing special. There is no propose call: they edit, and
the edit is recorded because it has nowhere else to go.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.enterprise_reference import (
    GLOBAL_ARTIFACT_ENTITY_TYPE,
    GLOBAL_ARTIFACT_ID,
    GLOBAL_ARTIFACT_KIND,
)
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

ENTERPRISE = "REQ@1712870400.eeeeeee.two-tier-repositories"
REFERENCE = "GAR@1780000001.bbbbbbb.two-tier-repositories"
LOCAL = "REQ@1780000004.ddddddd.a-local-requirement"


def _reference_md() -> str:
    return (
        "---\n"
        f"artifact-id: {REFERENCE}\n"
        "artifact-type: global-artifact-reference\n"
        "name: Two-tier repositories\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        f"{GLOBAL_ARTIFACT_ID}: {ENTERPRISE}\n"
        # Through the constants, not spelled again: this fixture said `global-artifact-kind`,
        # which is not the field, and every test here passed because nothing read the kind.
        f"{GLOBAL_ARTIFACT_KIND}: entity\n"
        f"{GLOBAL_ARTIFACT_ENTITY_TYPE}: requirement\n"
        "---\n\n<!-- §content -->\n\n"
        "## Two-tier repositories\n\nA proxy.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
        "<!-- §display -->\n"
    )


def _local_md() -> str:
    return (
        "---\n"
        f"artifact-id: {LOCAL}\n"
        "artifact-type: requirement\n"
        "name: A local requirement\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n<!-- §content -->\n\n"
        "## A local requirement\n\nOurs to edit.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
        "<!-- §display -->\n"
    )


def _enterprise_md() -> str:
    return (
        "---\n"
        f"artifact-id: {ENTERPRISE}\n"
        "artifact-type: requirement\n"
        "name: Two-tier repositories\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n<!-- §content -->\n\n"
        "## Two-tier repositories\n\nThe enterprise wording.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
        "<!-- §display -->\n"
    )


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    """Both tiers mounted, which is what a non-admin deployment actually has.

    Without the enterprise artifact present, staleness is undecidable and every change reads
    `current` whatever revision it recorded — which hid a real bug: the base was being taken from the
    *reference* file rather than from what it stands for, so every change would have read `stale` the
    moment a real workspace mounted the enterprise repository.
    """
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    (enterprise / "model" / "motivation" / "requirement" / f"{ENTERPRISE}.md").write_text(
        _enterprise_md(), encoding="utf-8"
    )
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    (root / "model" / "motivation" / "requirement").mkdir(parents=True)
    (root / "model" / "common" / "global-artifact-reference" / f"{REFERENCE}.md").write_text(
        _reference_md(), encoding="utf-8"
    )
    (root / "model" / "motivation" / "requirement" / f"{LOCAL}.md").write_text(_local_md(), encoding="utf-8")
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    return root, ArtifactRepository(index)


def _edit(workspace, artifact_id: str, *, with_repo: bool = True, **fields):  # noqa: ANN001, ANN003, ANN202
    root, repo = workspace
    catalogs = process_runtime_catalogs()
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

    return edit_entity(
        repo_root=root,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        verifier=build_artifact_verifier(catalogs=catalogs),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=artifact_id,
        repo=repo if with_repo else None,
        dry_run=False,
        **fields,
    )


def _changes(workspace):  # noqa: ANN001, ANN202
    _root, repo = workspace
    repo.refresh()
    return pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))


# ── the hole this closes ─────────────────────────────────────────────────────


def test_editing_enterprise_content_records_a_change_rather_than_failing(workspace) -> None:  # noqa: ANN001
    """This used to return `E140` — the reference losing the field that names its target."""
    result = _edit(workspace, REFERENCE, summary="Changed wording.")

    assert result.wrote, result.verification or result.warnings
    assert ENTERPRISE in _changes(workspace)


def test_the_reference_itself_is_left_alone(workspace) -> None:  # noqa: ANN001
    """The corruption the old path produced: writing the fields onto the proxy."""
    root, _repo = workspace
    before = (root / "model" / "common" / "global-artifact-reference" / f"{REFERENCE}.md").read_text(
        encoding="utf-8"
    )
    _edit(workspace, REFERENCE, summary="Changed wording.")

    assert (root / "model" / "common" / "global-artifact-reference" / f"{REFERENCE}.md").read_text(
        encoding="utf-8"
    ) == before


def test_the_change_records_what_the_author_gave_and_nothing_else(workspace) -> None:  # noqa: ANN001
    """The sentinel is the vocabulary: a field nobody mentioned must not be claimed as blanked."""
    _edit(workspace, REFERENCE, summary="Changed wording.")

    (change,) = _changes(workspace)[ENTERPRISE]
    assert change.edit.fields == {"summary": "Changed wording."}


def test_it_is_addressed_to_the_enterprise_artifact_not_the_reference(workspace) -> None:  # noqa: ANN001
    """A change is against the promoted artifact; the reference is only how this repository reaches
    it."""
    _edit(workspace, REFERENCE, summary="Changed wording.")

    (change,) = _changes(workspace)[ENTERPRISE]
    assert change.target_id == ENTERPRISE
    assert change.edit.artifact_id == ENTERPRISE


# ── ordinary content is untouched by any of this ─────────────────────────────


def test_a_local_entity_is_still_edited_directly(workspace) -> None:  # noqa: ANN001
    result = _edit(workspace, LOCAL, summary="Edited in place.")

    assert result.wrote
    assert _changes(workspace) == {}


def test_editing_a_local_entity_changes_its_file(workspace) -> None:  # noqa: ANN001
    root, _repo = workspace
    _edit(workspace, LOCAL, summary="Edited in place.")

    assert "Edited in place." in (
        root / "model" / "motivation" / "requirement" / f"{LOCAL}.md"
    ).read_text(encoding="utf-8")


# ── a second edit replaces the first ─────────────────────────────────────────


def test_a_second_edit_leaves_one_change_carrying_both_fields(workspace) -> None:  # noqa: ANN001
    """One change per artifact, arrived at through the ordinary edit path twice."""
    _edit(workspace, REFERENCE, summary="First wording.")
    _edit(workspace, REFERENCE, notes="And a note.")

    (change,) = _changes(workspace)[ENTERPRISE]
    assert change.edit.fields == {"summary": "First wording.", "notes": "And a note."}


def test_a_second_edit_of_one_field_wins(workspace) -> None:  # noqa: ANN001
    _edit(workspace, REFERENCE, summary="First wording.")
    _edit(workspace, REFERENCE, summary="Second wording.")

    (change,) = _changes(workspace)[ENTERPRISE]
    assert change.edit.fields == {"summary": "Second wording."}
    assert change.state == "draft"


# ── refusals that explain ────────────────────────────────────────────────────


def test_an_edit_that_changes_nothing_is_refused_with_a_reason(workspace) -> None:  # noqa: ANN001
    result = _edit(workspace, REFERENCE)

    assert not result.wrote
    assert any("changes nothing" in warning for warning in result.warnings)


def test_a_caller_with_no_repository_is_told_what_is_happening(workspace) -> None:  # noqa: ANN001
    """Strictly better than `E140`: it names the enterprise artifact and says the edit would be a
    change awaiting review."""
    result = _edit(workspace, REFERENCE, with_repo=False, summary="Changed wording.")

    assert not result.wrote
    assert any(ENTERPRISE in warning and "awaiting review" in warning for warning in result.warnings)


# ── the base a change records ────────────────────────────────────────────────


def test_a_change_records_the_revision_of_the_enterprise_artifact(workspace) -> None:  # noqa: ANN001
    """Not the reference's. The standing compares the recorded value against the enterprise
    artifact's revision to decide staleness, so a base taken from the wrong file makes every change
    read stale from the moment it is recorded."""
    from src.application.modeling.proposal_standing import enterprise_revision

    _root, repo = workspace
    _edit(workspace, REFERENCE, summary="Changed wording.")

    (change,) = _changes(workspace)[ENTERPRISE]
    assert change.base_revision == enterprise_revision(repo, ENTERPRISE)


def test_a_freshly_recorded_change_reads_as_current(workspace) -> None:  # noqa: ANN001
    """The property the wrong base broke: nothing upstream has moved, so nothing is stale."""
    from src.application.modeling.proposal_standing import standing_reader
    from src.domain.baseline_standing import Proposed

    _root, repo = workspace
    _edit(workspace, REFERENCE, summary="Changed wording.")
    repo.refresh()

    standing = standing_reader(repo)(ENTERPRISE)
    assert isinstance(standing, Proposed)
    assert standing.condition == "current"
