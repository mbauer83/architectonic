"""A change records the fields the artifact it changes actually has.

A global artifact reference stands for an entity, a document or a diagram, and which one decides the
vocabulary an edit of it may use: a change to a promoted document says `title` and `body`, and a
change to a promoted requirement says `summary` and `properties`. The capture path assumed `entity`,
and this repository already holds a reference to a promoted *document* — so that change would have
been recorded under the wrong catalogue and refused at replay, in front of a reviewer rather than its
author.

Deriving the kind uncovered two further defects, both of which have their own tests here because
both make the feature fail rather than merely mis-record:

* the base revision was taken with `get_entity`, which answers nothing for a document — so the change
  recorded an empty `base-revision` and was refused by `E148`, a message about a field the author
  never saw;
* the same blank was recorded whenever the enterprise repository is **not mounted**, which is the
  ordinary shape of an engagement deployment and the one this whole feature exists for.
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
from src.application.modeling.proposal_standing import (
    enterprise_revision,
    pending_proposals,
    standing_reader,
)
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE, UNKNOWN_BASE
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.document import edit_document
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

DOCUMENT = "STD@1712870400.ddddddd.a-promoted-standard"
DOCUMENT_REFERENCE = "GAR@1780000010.aaaaaaa.a-promoted-standard"
ENTITY = "REQ@1712870400.eeeeeee.a-promoted-requirement"
ENTITY_REFERENCE = "GAR@1780000011.bbbbbbb.a-promoted-requirement"


def _reference_md(reference_id: str, *, target: str, kind: str, name: str, entity_type: str | None) -> str:
    entity_type_line = f"{GLOBAL_ARTIFACT_ENTITY_TYPE}: {entity_type}\n" if entity_type else ""
    return (
        "---\n"
        f"artifact-id: {reference_id}\n"
        "artifact-type: global-artifact-reference\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        f"{GLOBAL_ARTIFACT_ID}: {target}\n"
        f"{GLOBAL_ARTIFACT_KIND}: {kind}\n"
        f"{entity_type_line}"
        "---\n\n<!-- §content -->\n\n"
        f"## {name}\n\nA proxy.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
        "<!-- §display -->\n"
    )


def _entity_md() -> str:
    return (
        "---\n"
        f"artifact-id: {ENTITY}\n"
        "artifact-type: requirement\n"
        "name: A promoted requirement\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n<!-- §content -->\n\n"
        "## A promoted requirement\n\nThe enterprise wording.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
        "<!-- §display -->\n"
    )


def _document_md() -> str:
    return (
        "---\n"
        f"artifact-id: {DOCUMENT}\n"
        "artifact-type: document\n"
        "doc-type: adr\n"
        "title: A promoted standard\n"
        "status: active\n"
        "---\n\n"
        "The enterprise wording.\n"
    )


def _engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    (root / "model" / "common" / "global-artifact-reference" / f"{DOCUMENT_REFERENCE}.md").write_text(
        _reference_md(
            DOCUMENT_REFERENCE, target=DOCUMENT, kind="document",
            name="A promoted standard", entity_type=None,
        ),
        encoding="utf-8",
    )
    (root / "model" / "common" / "global-artifact-reference" / f"{ENTITY_REFERENCE}.md").write_text(
        _reference_md(
            ENTITY_REFERENCE, target=ENTITY, kind="entity",
            name="A promoted requirement", entity_type="requirement",
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def both_tiers(tmp_path: Path):  # noqa: ANN201
    """An admin deployment: the enterprise artifacts are readable, so their revisions are too."""
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    (enterprise / "model" / "motivation" / "requirement" / f"{ENTITY}.md").write_text(
        _entity_md(), encoding="utf-8"
    )
    (enterprise / "docs" / "adr").mkdir(parents=True)
    (enterprise / "docs" / "adr" / f"{DOCUMENT}.md").write_text(_document_md(), encoding="utf-8")
    root = _engagement_root(tmp_path)
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    return root, ArtifactRepository(index)


@pytest.fixture()
def engagement_only(tmp_path: Path):  # noqa: ANN201
    """The ordinary deployment: references, and nothing of what they stand for."""
    process_runtime_catalogs()
    root = _engagement_root(tmp_path)
    index = shared_artifact_index([root])
    index.refresh()
    return root, ArtifactRepository(index)


def _edit_document(workspace, artifact_id: str, **fields):  # noqa: ANN001, ANN003, ANN202
    root, repo = workspace
    from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root

    defaults: dict[str, object] = {
        "title": None, "body": None, "keywords": None, "extra_frontmatter": None,
        "status": None, "version": None, "last_updated": None,
    }
    return edit_document(
        assert_write_root=assert_engagement_write_root,
        repo_root=root,
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=artifact_id,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        repo=repo,
        dry_run=False,
        **{**defaults, **fields},
    )


def _edit_entity(workspace, artifact_id: str, **fields):  # noqa: ANN001, ANN003, ANN202
    root, repo = workspace
    return edit_entity(
        repo_root=root,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=artifact_id,
        repo=repo,
        dry_run=False,
        **fields,
    )


def _changes(workspace):  # noqa: ANN001, ANN202
    _root, repo = workspace
    repo.refresh()
    return pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))


# ── the kind comes from the reference ────────────────────────────────────────


def test_editing_a_promoted_document_records_a_document_change(both_tiers) -> None:  # noqa: ANN001
    """Through the document edit, which never found the reference before: it resolves under `docs/`,
    and a reference lives in the model tree."""
    result = _edit_document(both_tiers, DOCUMENT_REFERENCE, title="A better title")

    assert result.wrote, result.verification or result.warnings
    (change,) = _changes(both_tiers)[DOCUMENT]
    assert change.edit.kind == "document"
    assert change.edit.fields == {"title": "A better title"}


def test_a_document_change_is_addressed_to_the_document(both_tiers) -> None:  # noqa: ANN001
    _edit_document(both_tiers, DOCUMENT_REFERENCE, title="A better title")

    (change,) = _changes(both_tiers)[DOCUMENT]
    assert change.target_id == DOCUMENT


def test_an_entity_edit_of_a_document_reference_is_refused_by_kind(both_tiers) -> None:  # noqa: ANN001
    """The defect stated as a refusal: entity fields have no meaning for a document, and saying so
    here is the difference between the author correcting it and a reviewer discovering it."""
    result = _edit_entity(both_tiers, DOCUMENT_REFERENCE, summary="Entity wording.")

    assert not result.wrote
    assert any("stands for a document" in warning for warning in result.warnings)
    assert _changes(both_tiers) == {}


def test_a_document_edit_of_an_entity_reference_is_refused_by_kind(both_tiers) -> None:  # noqa: ANN001
    result = _edit_document(both_tiers, ENTITY_REFERENCE, title="Document wording.")

    assert not result.wrote
    assert any("stands for a entity" in warning for warning in result.warnings)


def test_the_refusal_names_the_artifact_rather_than_its_id(both_tiers) -> None:  # noqa: ANN001
    result = _edit_entity(both_tiers, DOCUMENT_REFERENCE, summary="Entity wording.")

    assert any("A promoted standard" in warning for warning in result.warnings)


# ── the base revision answers for every kind ─────────────────────────────────


def test_the_revision_of_a_promoted_document_can_be_taken(both_tiers) -> None:  # noqa: ANN001
    """`get_entity` answered None here, which is how the blank base reached E148."""
    _root, repo = both_tiers

    assert enterprise_revision(repo, DOCUMENT) is not None


def test_a_document_change_records_that_revision(both_tiers) -> None:  # noqa: ANN001
    _root, repo = both_tiers
    _edit_document(both_tiers, DOCUMENT_REFERENCE, title="A better title")

    (change,) = _changes(both_tiers)[DOCUMENT]
    assert change.base_revision == enterprise_revision(repo, DOCUMENT)


def test_the_repository_resolves_a_file_of_any_kind(both_tiers) -> None:  # noqa: ANN001
    """The delegation this needed, verified directly: one lookup, three kinds, both tiers."""
    _root, repo = both_tiers

    assert repo.find_file_by_id(ENTITY) is not None
    assert repo.find_file_by_id(DOCUMENT) is not None
    assert repo.find_file_by_id(DOCUMENT_REFERENCE) is not None


# ── a deployment that mounts no enterprise content ───────────────────────────


def test_a_change_is_recorded_where_the_enterprise_repository_is_absent(engagement_only) -> None:  # noqa: ANN001
    """The regression: the blank base was refused by E148, so the ordinary deployment — the one this
    feature exists for — could record no change at all."""
    result = _edit_entity(engagement_only, ENTITY_REFERENCE, summary="Changed wording.")

    assert result.wrote, result.verification or result.warnings


def test_that_change_is_visible_rather_than_silently_undecodable(engagement_only) -> None:  # noqa: ANN001
    """A base the reader refuses is a change nobody can see — worse than one that fails loudly."""
    _edit_entity(engagement_only, ENTITY_REFERENCE, summary="Changed wording.")

    (change,) = _changes(engagement_only)[ENTITY]
    assert change.base_revision == UNKNOWN_BASE


def test_an_unknown_base_reads_as_current_rather_than_stale(engagement_only) -> None:  # noqa: ANN001
    """Undecidable, not moved. Guessing the alarming way costs the author a rebase they never needed."""
    from src.domain.baseline_standing import Proposed

    _root, repo = engagement_only
    _edit_entity(engagement_only, ENTITY_REFERENCE, summary="Changed wording.")
    repo.refresh()

    standing = standing_reader(repo)(ENTITY)
    assert isinstance(standing, Proposed)
    assert standing.condition == "current"


# ── the artifact addressed by its own id, which is the only way a person reaches it ──


def test_editing_a_promoted_artifact_by_its_own_id_records_a_change(both_tiers) -> None:  # noqa: ANN001
    """The path a person actually takes, and the one that used to write upstream.

    References are excluded from every list and every search on purpose, so a reader finds the
    promoted artifact itself and edits *that*. The interception recognised only a reference, and the
    guard beside it checks the root a write was handed rather than the file it is about to touch — so
    an engagement deployment editing an enterprise artifact by its own id passed the guard and
    modified the enterprise repository, with no change recorded and `wrote: true`.
    """
    result = _edit_entity(both_tiers, ENTITY, summary="A proposed wording.")

    assert result.wrote, result.verification or result.warnings
    (change,) = _changes(both_tiers)[ENTITY]
    assert change.edit.fields == {"summary": "A proposed wording."}


def test_the_enterprise_file_is_left_exactly_as_it_was(both_tiers) -> None:  # noqa: ANN001
    """The integrity claim, stated over the bytes."""
    root, _repo = both_tiers
    enterprise = root.parent.parent.parent / "enterprise-repository"
    path = enterprise / "model" / "motivation" / "requirement" / f"{ENTITY}.md"
    before = path.read_text(encoding="utf-8")

    _edit_entity(both_tiers, ENTITY, summary="A proposed wording.")

    assert path.read_text(encoding="utf-8") == before


def test_the_change_is_held_against_the_reference_that_already_stood_for_it(both_tiers) -> None:  # noqa: ANN001
    """One reference per promoted artifact: an edit by enterprise id uses the one that exists rather
    than making a second."""
    _edit_entity(both_tiers, ENTITY, summary="A proposed wording.")

    (change,) = _changes(both_tiers)[ENTITY]
    assert change.reference_id == ENTITY_REFERENCE


def test_a_promoted_artifact_with_no_reference_gets_one(tmp_path: Path) -> None:
    """A change names a *local* reference, and the engagement holds one only for what it promoted
    itself. Ensuring it is what promotion does, the operation is idempotent, and it stays invisible
    like every other reference — an edit that needs an anchor makes one."""
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    (enterprise / "model" / "motivation" / "requirement" / f"{ENTITY}.md").write_text(
        _entity_md(), encoding="utf-8"
    )
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    workspace = (root, ArtifactRepository(index))

    result = _edit_entity(workspace, ENTITY, summary="A proposed wording.")

    assert result.wrote, result.verification or result.warnings
    (change,) = _changes(workspace)[ENTITY]
    assert change.reference_id.startswith("GAR@")
