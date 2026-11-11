"""An ArchiMate diagram that labels, repeats or decorates an instance is still drawn from the model.

``diagram-entities`` means two different things depending on the diagram type. For a C4, sequence or
activity diagram it *is* the membership — the body is rendered from it ("standalone"). For an ArchiMate
diagram it holds only statements about instances the model already supplies: ``display_labels``,
``occurrence``, and since 0.11.0 ``display_icons`` and ``type_icons``. The membership stays
``entity-ids-used`` and the body stays generated from the model.

``is_standalone`` decided by the *shape* of the frontmatter key — any dict — and never asked the type,
so the first label or icon on an ArchiMate diagram silently changed who owns it: a membership edit was
refused with advice to pass ``diagram_entities``, and a sync kept references to a connection the model no
longer has instead of reconciling them away. Asserted through the MCP tools, because the defect is what a
write does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-OWN" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _goal(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="goal", name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _diagram(repo: Path, goals: list[str], diagram_entities: dict | None) -> str:
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Owned by the model", entity_ids=goals,
        diagram_entities=diagram_entities, dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    return str(created["artifact_id"])


def _frontmatter_ids(repo: Path, diagram_id: str, key: str) -> list[str]:
    import yaml  # noqa: PLC0415 — test-local reading of the file the write produced

    text = (repo / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml").read_text(encoding="utf-8")
    return list(yaml.safe_load(text.split("---", 2)[1]).get(key) or [])


STATEMENTS = [
    pytest.param(None, id="no-statement-control"),
    pytest.param({"display_labels": {}}, id="empty-labels"),
    pytest.param("LABEL", id="a-display-label"),
]


def _statement(kind: object, goal: str) -> dict | None:
    if kind is None:
        return None
    return {"display_labels": {goal: "Short"}} if kind == "LABEL" else dict(kind)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", STATEMENTS)
def test_its_membership_can_still_be_set_by_entity_ids(repo: Path, kind: object) -> None:
    first, second = _goal(repo, "First Goal"), _goal(repo, "Second Goal")
    diagram_id = _diagram(repo, [first, second], _statement(kind, first))

    result = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, entity_ids=[first], dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    assert _frontmatter_ids(repo, diagram_id, "entity-ids-used") == [first]


@pytest.mark.parametrize("kind", STATEMENTS)
def test_a_sync_reconciles_away_a_connection_the_model_no_longer_has(repo: Path, kind: object) -> None:
    first, second = _goal(repo, "First Goal"), _goal(repo, "Second Goal")
    added = mcp.artifact_add_connection(
        source_entity=first, connection_type="archimate-association", target_entity=second,
        dry_run=False, repo_root=str(repo),
    )
    assert added["wrote"], added
    diagram_id = _diagram(repo, [first, second], _statement(kind, first))
    assert _frontmatter_ids(repo, diagram_id, "connection-ids-used"), "the connection was not drawn"

    removed = mcp.artifact_edit_connection(
        source_entity=first, connection_type="archimate-association", target_entity=second,
        operation="remove", dry_run=False, repo_root=str(repo),
    )
    assert removed["wrote"], removed
    synced = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, puml="auto-sync", dry_run=False, repo_root=str(repo),
    )

    assert synced["wrote"], synced
    assert _frontmatter_ids(repo, diagram_id, "connection-ids-used") == []
