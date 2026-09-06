"""A reader asking "what have I changed locally?" gets an answer they can act on.

A change is stored addressed to an *enterprise* id, and a reader can act on neither that nor the
change file's own id: they cannot open the enterprise artifact, and they never authored the change.
So a row names the artifact the way this repository addresses it — through the reference standing for
it — and says what the change does in fields.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.change_overview import recorded_changes
from src.application.modeling.enterprise_reference import (
    GLOBAL_ARTIFACT_ID,
    GLOBAL_ARTIFACT_KIND,
    references_by_target,
)
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

FIRST = "REQ@1712870400.aaaaaaa.a-promoted-requirement"
FIRST_REF = "GAR@1780000020.aaaaaaa.a-promoted-requirement"
SECOND = "REQ@1712870400.bbbbbbb.another-promoted-requirement"
SECOND_REF = "GAR@1780000021.bbbbbbb.another-promoted-requirement"


def _entity_md(artifact_id: str, name: str) -> str:
    return (
        f"---\nartifact-id: {artifact_id}\nartifact-type: requirement\nname: {name}\n"
        "version: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n"
        f"## {name}\n\nThe enterprise wording.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n<!-- §display -->\n"
    )


def _reference_md(reference_id: str, target: str, name: str) -> str:
    return (
        f"---\nartifact-id: {reference_id}\nartifact-type: global-artifact-reference\nname: {name}\n"
        "version: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n"
        f"{GLOBAL_ARTIFACT_ID}: {target}\n{GLOBAL_ARTIFACT_KIND}: entity\n"
        "global-artifact-entity-type: requirement\n---\n\n<!-- §content -->\n\n"
        f"## {name}\n\nA proxy.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n<!-- §display -->\n"
    )


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    for artifact_id, name in ((FIRST, "Zebra crossings"), (SECOND, "Alpha channels")):
        (enterprise / "model" / "motivation" / "requirement" / f"{artifact_id}.md").write_text(
            _entity_md(artifact_id, name), encoding="utf-8"
        )
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    for reference_id, target, name in (
        (FIRST_REF, FIRST, "Zebra crossings"),
        (SECOND_REF, SECOND, "Alpha channels"),
    ):
        (root / "model" / "common" / "global-artifact-reference" / f"{reference_id}.md").write_text(
            _reference_md(reference_id, target, name), encoding="utf-8"
        )
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    return root, ArtifactRepository(index)


def _edit(workspace, artifact_id: str, **fields):  # noqa: ANN001, ANN003, ANN202
    root, repo = workspace
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

    result = edit_entity(
        repo_root=root,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=artifact_id,
        repo=repo,
        dry_run=False,
        **fields,
    )
    repo.refresh()
    return result


def test_a_repository_with_nothing_pending_holds_no_changes(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace

    assert recorded_changes(repo) == ()


def test_a_change_names_the_artifact_rather_than_its_enterprise_id(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Changed wording.")

    (row,) = recorded_changes(repo)
    assert row.target_name == "Zebra crossings"


def test_a_change_carries_the_reference_a_reader_can_open(workspace) -> None:  # noqa: ANN001
    """The enterprise id is not something this repository can show; the reference is."""
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Changed wording.")

    (row,) = recorded_changes(repo)
    assert row.reference_id == FIRST_REF
    assert row.target_id == FIRST


def test_a_change_says_which_fields_it_changes(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Changed wording.", notes="And a note.")

    (row,) = recorded_changes(repo)
    assert row.changed_fields == ("notes", "summary")
    assert row.kind == "entity"


def test_a_fresh_change_is_current_and_a_draft(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Changed wording.")

    (row,) = recorded_changes(repo)
    assert (row.state, row.condition) == ("draft", "current")


def test_a_change_goes_stale_when_the_enterprise_artifact_moves(workspace) -> None:  # noqa: ANN001
    """The whole point of recording a base: the reader is told before a reviewer has to."""
    root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Changed wording.")
    enterprise = root.parent.parent.parent / "enterprise-repository"
    path = enterprise / "model" / "motivation" / "requirement" / f"{FIRST}.md"
    path.write_text(path.read_text(encoding="utf-8").replace("enterprise wording", "moved on"), encoding="utf-8")
    repo.refresh()

    (row,) = recorded_changes(repo)
    assert row.condition == "stale"


def test_changes_are_ordered_by_the_artifact_they_change(workspace) -> None:  # noqa: ANN001
    """By name, which is the order a reader is scanning in — not by id, which orders by clock."""
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Zebra wording.")
    _edit(workspace, SECOND_REF, summary="Alpha wording.")

    assert [row.target_name for row in recorded_changes(repo)] == ["Alpha channels", "Zebra crossings"]


def test_the_reverse_lookup_finds_every_reference_once(workspace) -> None:  # noqa: ANN001
    """The map the overview is built on, and the duplicate check shares."""
    _root, repo = workspace

    found = references_by_target(repo.list_entities())
    assert {FIRST, SECOND} <= set(found)
    assert found[FIRST].artifact_id == FIRST_REF


# ── what a stale change shows ────────────────────────────────────────────────


def _move_the_enterprise_artifact(root: Path, wording: str) -> None:
    enterprise = root.parent.parent.parent / "enterprise-repository"
    path = enterprise / "model" / "motivation" / "requirement" / f"{FIRST}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("The enterprise wording.", wording), encoding="utf-8"
    )


def test_an_ordinary_change_shows_both_values_too(workspace) -> None:  # noqa: ANN001
    """This asserted the opposite, on the reasoning that a current change and the artifact agree.

    They do not. A change's fields differ from the artifact by definition — that is what makes them
    a change — and they agree only once it has been integrated, when it is closed. Restricting the
    values to stale changes left an author's own pending values visible nowhere but the edit form.
    """
    _root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Mine.")

    (row,) = recorded_changes(repo)
    assert row.condition == "current"
    assert [(d.field, d.proposed, d.current) for d in row.divergence] == [
        ("summary", "Mine.", "The enterprise wording.")
    ]


def test_a_stale_change_shows_what_it_asks_for_and_what_the_artifact_says(workspace) -> None:  # noqa: ANN001
    """"Stale" alone tells an author their work needs attention and nothing about what to do."""
    root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Mine.")
    _move_the_enterprise_artifact(root, "Someone else's wording.")
    repo.refresh()

    (row,) = recorded_changes(repo)
    assert row.condition == "stale"
    assert [(d.field, d.proposed, d.current) for d in row.divergence] == [
        ("summary", "Mine.", "Someone else's wording.")
    ]


def test_every_changed_field_is_shown_because_nothing_here_knows_which_one_moved(workspace) -> None:  # noqa: ANN001
    """A stale change shows both values for *all* its fields, not only for the one that moved.

    The recorded base is a content hash of the whole artifact, so nothing can say which field moved
    under the change and which was always different — and a change's fields differ from the artifact
    by definition, since that is what makes them a change. Showing all of them is the honest answer;
    filtering to "the ones that moved" would need a per-field base nothing records.
    """
    root, repo = workspace
    _edit(workspace, FIRST_REF, summary="Mine.", notes="Also mine.")
    _move_the_enterprise_artifact(root, "Someone else's wording.")
    repo.refresh()

    (row,) = recorded_changes(repo)
    assert [d.field for d in row.divergence] == ["notes", "summary"]


def test_a_field_the_artifact_has_no_reading_for_is_left_out(workspace) -> None:
    """Diverging from nothing is not a difference to show."""
    from src.application.modeling.change_overview import FieldDivergence, _divergence
    from src.application.modeling.proposal_edit import ProposalEdit
    from src.application.modeling.proposal_standing import PendingProposal

    proposal = PendingProposal(
        proposal_id="PCH@1", target_id=FIRST, reference_id=FIRST_REF,
        changed_fields=("summary",), base_revision="r", state="draft",
        edit=ProposalEdit(kind="entity", artifact_id=FIRST, fields={"summary": "Mine."}),
    )

    assert _divergence(proposal, {"summary": None}) == ()
    assert _divergence(proposal, {}) == ()
    assert _divergence(proposal, None) == ()
    assert _divergence(proposal, {"summary": "Theirs."}) == (
        FieldDivergence(field="summary", proposed="Mine.", current="Theirs."),
    )


def test_a_structured_value_names_the_field_without_inventing_a_rendering(workspace) -> None:
    """A properties table has no single line to show, and making one up here would be a second,
    worse spelling of what the artifact view already draws."""
    from src.application.modeling.change_overview import _divergence
    from src.application.modeling.proposal_edit import ProposalEdit
    from src.application.modeling.proposal_standing import PendingProposal

    proposal = PendingProposal(
        proposal_id="PCH@1", target_id=FIRST, reference_id=FIRST_REF,
        changed_fields=("properties",), base_revision="r", state="draft",
        edit=ProposalEdit(kind="entity", artifact_id=FIRST, fields={"properties": {"a": "1"}}),
    )

    (shown,) = _divergence(proposal, {"properties": {"a": "2"}})
    assert (shown.field, shown.proposed, shown.current) == ("properties", None, None)
