"""The two operations that make a recorded change something an author holds rather than suffers.

Editing an artifact this repository does not own records a change instead of writing. Until there
was a way to see what was recorded and to take one back, the recording was something that happened
to a session and never appeared again — which is the difference between a feature and a side effect.

Over the MCP tools, because they and the REST routes are two spellings of the same two operations and
these are the ones an agent reaches for. The REST pair is checked by the route-policy fitness
functions for its address, its authorization identity and its response contract; what neither of
those can check is that discarding actually ends a change and that listing then omits it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.change_overview import recorded_changes
from src.application.modeling.enterprise_reference import GLOBAL_ARTIFACT_ID, GLOBAL_ARTIFACT_KIND
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSAL_STATE, PROPOSED_CHANGE_TYPE
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.entity_edit import edit_entity
from src.infrastructure.write.artifact_write.proposal_lifecycle import mark_proposal_state

TARGET = "REQ@1712870400.ccccccc.a-promoted-requirement"
REFERENCE = "GAR@1780000030.ccccccc.a-promoted-requirement"


def _entity_md() -> str:
    return (
        f"---\nartifact-id: {TARGET}\nartifact-type: requirement\nname: A promoted requirement\n"
        "version: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n"
        "## A promoted requirement\n\nThe enterprise wording.\n\n"
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


@pytest.fixture()
def workspace(tmp_path: Path):  # noqa: ANN201
    process_runtime_catalogs()
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model" / "motivation" / "requirement").mkdir(parents=True)
    (enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md").write_text(
        _entity_md(), encoding="utf-8"
    )
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model" / "common" / "global-artifact-reference").mkdir(parents=True)
    (root / "model" / "common" / "proposed-change").mkdir(parents=True)
    (root / "model" / "common" / "global-artifact-reference" / f"{REFERENCE}.md").write_text(
        _reference_md(), encoding="utf-8"
    )
    index = combined_artifact_index(root, enterprise)
    index.refresh()
    return root, ArtifactRepository(index)


def _record_a_change(workspace) -> str:  # noqa: ANN001
    root, repo = workspace
    edit_entity(
        repo_root=root,
        registry=ArtifactRegistry(repo._store),  # noqa: SLF001 — the write path is handed one
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        artifact_id=REFERENCE,
        repo=repo,
        summary="Changed wording.",
        dry_run=False,
    )
    repo.refresh()
    (change,) = recorded_changes(repo)
    return change.change_id


def test_a_recorded_change_is_listed(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace
    change_id = _record_a_change(workspace)

    assert [row.change_id for row in recorded_changes(repo)] == [change_id]


def test_discarding_ends_the_change(workspace) -> None:  # noqa: ANN001
    _root, repo = workspace
    change_id = _record_a_change(workspace)
    record = repo.get_entity(change_id)
    assert record is not None

    assert mark_proposal_state(record.path, artifact_id=change_id, state="abandoned")


def test_a_discarded_change_is_no_longer_listed(workspace) -> None:  # noqa: ANN001
    """The behaviour that matters: an author who takes a change back stops holding it."""
    _root, repo = workspace
    change_id = _record_a_change(workspace)
    record = repo.get_entity(change_id)
    assert record is not None
    mark_proposal_state(record.path, artifact_id=change_id, state="abandoned")
    repo.refresh()

    assert recorded_changes(repo) == ()
    assert pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)) == {}


def test_the_record_survives_being_discarded(workspace) -> None:  # noqa: ANN001
    """Terminal, not deleted. A submitted change has been seen by someone, and its disappearance
    would be indistinguishable from it never having existed."""
    _root, repo = workspace
    change_id = _record_a_change(workspace)
    record = repo.get_entity(change_id)
    assert record is not None
    mark_proposal_state(record.path, artifact_id=change_id, state="abandoned")
    repo.refresh()

    ended = repo.get_entity(change_id)
    assert ended is not None
    assert ended.extra.get(PROPOSAL_STATE) == "abandoned"


def test_discarding_twice_reports_that_nothing_changed(workspace) -> None:  # noqa: ANN001
    """Idempotent at the file level; the surfaces refuse the second call before reaching here."""
    _root, repo = workspace
    change_id = _record_a_change(workspace)
    record = repo.get_entity(change_id)
    assert record is not None
    mark_proposal_state(record.path, artifact_id=change_id, state="abandoned")

    assert not mark_proposal_state(record.path, artifact_id=change_id, state="abandoned")
