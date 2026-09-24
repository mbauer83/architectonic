"""Editing the nodes of a diagram whose nodes are its body re-renders the body and the picture.

A GSN argument's nodes are hosted by the diagram, in `diagram-entities`, and GSN declares no
diagram-owned entity types. The edit path inferred "render from the entities" from that
declaration, so an edit of a GSN case's nodes wrote the new names into the frontmatter and left the
body and the rendered SVG showing the old ones — `auto-sync` included. Creation had always rendered
from the entities, so a new case looked right and only its first edit went stale.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.app_bootstrap import process_runtime_catalogs


def _case(goal: str) -> dict:
    return {
        "nodes": [
            {"node_id": "g1", "name": goal, "gsn_type": "goal"},
            {"node_id": "sn1", "name": "Evidence suite", "gsn_type": "solution"},
        ],
        "edges": [{"source_id": "g1", "target_id": "sn1", "conn_type": "supported-by"}],
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def test_editing_a_gsn_case_s_nodes_re_renders_its_body(repo: Path) -> None:
    from src.infrastructure.mcp import mcp_artifact_server as mcp

    created = mcp.artifact_create_diagram(
        diagram_type="gsn", name="Case", diagram_entities=_case("The old claim"), dry_run=False,
        repo_root=str(repo),
    )
    assert created["wrote"], created
    path = Path(created["path"])

    edited = mcp.artifact_edit_diagram(
        artifact_id=created["artifact_id"], diagram_entities=_case("The new claim"), dry_run=False,
        repo_root=str(repo),
    )

    assert edited["wrote"], edited
    body = path.read_text(encoding="utf-8").split("@startuml", 1)[1]
    assert "The new claim" in body and "The old claim" not in body


def test_gsn_says_its_nodes_are_its_body_and_the_store_projections_do_not() -> None:
    """Asked of the classes, not the catalog: bowtie and control structure register only where a
    confidential store is configured, which this process may not have. Those two are projections of
    the store — their nodes exist there, with connections no diagram shows — so an edit must not
    redraw them from whatever a caller put in `diagram-entities`."""
    from src.diagram_types.bowtie import _BowtieDiagramType
    from src.diagram_types.control_structure import _ControlStructureDiagramType
    from src.diagram_types.gsn import _GsnDiagramType

    assert _GsnDiagramType.__dict__["body_is_rendered_from_diagram_entities"].fget(None) is True
    for cls in (_BowtieDiagramType, _ControlStructureDiagramType):
        assert "body_is_rendered_from_diagram_entities" not in cls.__dict__, cls.__name__


@pytest.mark.parametrize("diagram_type", ["archimate-application", "archimate-layered", "matrix"])
def test_a_body_the_diagram_owns_is_not_rendered_from_its_metadata(diagram_type: str) -> None:
    module = process_runtime_catalogs().diagram_types.find_diagram_type(diagram_type)

    assert module is not None and not module.body_is_rendered_from_diagram_entities


def test_every_type_that_declares_its_own_entity_types_renders_from_them() -> None:
    catalogs = process_runtime_catalogs().diagram_types
    for name in catalogs.all_diagram_types():
        module = catalogs.find_diagram_type(name)
        if module is not None and module.ui_config.diagram_only_types:
            assert module.body_is_rendered_from_diagram_entities, name
