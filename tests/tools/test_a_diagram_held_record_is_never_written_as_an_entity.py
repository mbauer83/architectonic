"""A record a diagram holds is never written as an entity of its own (B109).

A diagram-only record — a swimlane, an action, a note — lives inside its diagram's ``diagram-entities``
and has no file. The registry used to answer its *host diagram's* file when asked for the record's, so
an entity delete addressed to a note unlinked the whole diagram, an edit parsed the diagram as an
entity, a connection wrote an outgoing file beside it, and a promotion copied it upstream. The
registry now gives such a record no file, and every entity write refuses it and names the diagram.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion
from tests.support.diagram_held_records import (
    ACTION_ID,
    DIAGRAM,
    DIAGRAM_ID,
    NOTE_ID,
    diagram_file,
    repository_with_held_records,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return repository_with_held_records(tmp_path, "ENG-HELD")


def _diagram_file(repo: Path) -> Path:
    return diagram_file(repo)


def _goal(repo: Path) -> str:
    created = mcp.artifact_create_entity(
        artifact_type="goal", name="A goal", summary="Summary", dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    return str(created["artifact_id"])


def test_the_registry_gives_a_held_record_no_file_but_still_finds_its_diagram(repo: Path) -> None:
    registry = ArtifactRegistry(shared_artifact_index([repo]))

    assert NOTE_ID in registry.entity_ids(), "the record is indexed"
    assert registry.find_file_by_id(NOTE_ID) is None
    assert registry.find_file_by_id(DIAGRAM_ID) == _diagram_file(repo)


def test_deleting_a_held_record_is_refused_and_the_diagram_survives(repo: Path) -> None:
    with pytest.raises(ValueError, match=r"held by diagram .*artifact_edit_diagram") as refused:
        mcp.artifact_delete_entity(artifact_id=NOTE_ID, dry_run=False, repo_root=str(repo))

    assert DIAGRAM_ID in str(refused.value)
    assert _diagram_file(repo).read_text(encoding="utf-8") == DIAGRAM


def test_editing_a_held_record_as_an_entity_is_refused(repo: Path) -> None:
    with pytest.raises(ValueError, match="held by diagram"):
        mcp.artifact_edit_entity(artifact_id=ACTION_ID, name="Renamed", dry_run=False, repo_root=str(repo))

    assert _diagram_file(repo).read_text(encoding="utf-8") == DIAGRAM


@pytest.mark.parametrize("held_end", ["source", "target"])
def test_a_model_connection_never_names_a_held_record(repo: Path, held_end: str) -> None:
    goal = _goal(repo)
    ends = {"source_entity": NOTE_ID, "target_entity": goal} if held_end == "source" else \
           {"source_entity": goal, "target_entity": NOTE_ID}

    with pytest.raises(ValueError, match="held by diagram"):
        mcp.artifact_add_connection(
            connection_type="archimate-association", dry_run=False, repo_root=str(repo), **ends,
        )

    assert not list(_diagram_file(repo).parent.glob("*.outgoing.md")), "nothing written beside the diagram"


def test_the_bulk_delete_refuses_a_held_record_too(repo: Path) -> None:
    result = mcp.artifact_bulk_delete(
        items=[{"op": "delete_entity", "artifact_id": NOTE_ID}], dry_run=False, repo_root=str(repo),
    )

    assert result["batch_verification"]["executed"] is False, result
    assert "held by diagram" in str(result["results"][0]["error"]), result["results"][0]
    assert _diagram_file(repo).read_text(encoding="utf-8") == DIAGRAM


def test_promoting_a_held_record_on_its_own_is_refused(repo: Path, tmp_path: Path) -> None:
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model").mkdir(parents=True)
    index = combined_artifact_index(repo, enterprise)

    with pytest.raises(ValueError, match="held by diagram"):
        plan_promotion(
            None, ArtifactRegistry(index), ArtifactRepository(index),
            entity_ids=[NOTE_ID], engagement_root=repo, enterprise_root=enterprise,
        )
