"""Regression tests: diagram-only read contract for node_id-style diagram formats (GSN).

Reproduces the confirmed defect where artifact_query_read_artifact returned null
for diagram-only ids whose format uses 'node_id' instead of 'id'.
"""

from __future__ import annotations

from pathlib import Path

from src.application._diagram_entity_extraction import (
    _is_connection_item,
)
from src.application._diagram_entity_extraction import (
    diagram_local_to_full as _diagram_local_to_full,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_connections as _extract_diagram_connections,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_entities as _extract_diagram_entities,
)
from src.application.artifact_query import ArtifactRepository
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.artifact_index import shared_artifact_index

# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_GSN_ID = "GSN@1234567890.gSnXxX.my-assurance-case"
_GSN_FILE = "diagram-catalog/diagrams/GSN@1234567890.gSnXxX.my-assurance-case.puml"

_GSN_DIAGRAM_CONTENT = f"""\
---
artifact-id: {_GSN_ID}
artifact-type: diagram
name: "My Assurance Case"
diagram-type: gsn
version: 0.1.0
status: draft
diagram-entities:
  nodes:
  - node_id: g1
    name: The system is acceptably secure
    gsn_type: goal
  - node_id: s1
    name: Argue over the security constraints
    gsn_type: strategy
  - node_id: cx1
    name: Scope
    gsn_type: context
  edges:
  - source_id: g1
    target_id: s1
    conn_type: supported-by
  - source_id: g1
    target_id: cx1
    conn_type: in-context-of
---
@startuml my-assurance-case
top to bottom direction

rectangle "G: The system is acceptably secure" as g1 #D0E8FF
card "S: Argue over the security constraints" as s1 #E8E0FF
usecase "C: Scope" as cx1 #FFFFD0

g1 --> s1 : supported-by
g1 ..> cx1 : in-context-of

@enduml
"""


def _make_gsn_diagram_record() -> DiagramRecord:
    return DiagramRecord(
        artifact_id=_GSN_ID,
        artifact_type="diagram",
        name="My Assurance Case",
        diagram_type="gsn",
        version="0.1.0",
        status="draft",
        path=Path("/tmp/my-assurance-case.puml"),
        extra={
            "diagram-entities": {
                "nodes": [
                    {"node_id": "g1", "name": "The system is acceptably secure", "gsn_type": "goal"},
                    {"node_id": "s1", "name": "Argue over the security constraints", "gsn_type": "strategy"},
                    {"node_id": "cx1", "name": "Scope", "gsn_type": "context"},
                ],
                "edges": [
                    {"source_id": "g1", "target_id": "s1", "conn_type": "supported-by"},
                    {"source_id": "g1", "target_id": "cx1", "conn_type": "in-context-of"},
                ],
            }
        },
    )


# ── unit: _is_connection_item ─────────────────────────────────────────────────


def test_is_connection_item_true_for_gsn_edge() -> None:
    edge = {"source_id": "g1", "target_id": "s1", "conn_type": "supported-by"}
    assert _is_connection_item(edge) is True


def test_is_connection_item_false_for_gsn_node() -> None:
    node = {"node_id": "g1", "name": "Goal", "gsn_type": "goal"}
    assert _is_connection_item(node) is False


def test_is_connection_item_false_for_activity_action() -> None:
    action = {"id": "a1", "label": "Submit"}
    assert _is_connection_item(action) is False


# ── unit: _extract_diagram_entities with node_id ─────────────────────────────


def test_extract_gsn_nodes_via_node_id() -> None:
    diag = _make_gsn_diagram_record()
    entities = _extract_diagram_entities(diag)
    # 3 nodes, 0 edges (edges are connection-items, skipped)
    assert len(entities) == 3
    ids = {e.artifact_id for e in entities}
    assert f"{_GSN_ID}#nodes/g1" in ids
    assert f"{_GSN_ID}#nodes/s1" in ids
    assert f"{_GSN_ID}#nodes/cx1" in ids


def test_extract_gsn_nodes_display_alias_matches_node_id() -> None:
    diag = _make_gsn_diagram_record()
    entities = _extract_diagram_entities(diag)
    alias_map = {e.artifact_id: e.display_alias for e in entities}
    assert alias_map[f"{_GSN_ID}#nodes/g1"] == "g1"
    assert alias_map[f"{_GSN_ID}#nodes/cx1"] == "cx1"


def test_extract_gsn_nodes_name_populated() -> None:
    diag = _make_gsn_diagram_record()
    entities = {e.artifact_id: e for e in _extract_diagram_entities(diag)}
    assert entities[f"{_GSN_ID}#nodes/g1"].name == "The system is acceptably secure"


def test_extract_gsn_nodes_host_diagram_id_set() -> None:
    diag = _make_gsn_diagram_record()
    entities = _extract_diagram_entities(diag)
    for e in entities:
        assert e.host_diagram_id == _GSN_ID


def test_extract_gsn_content_text_excludes_node_id() -> None:
    diag = _make_gsn_diagram_record()
    entities = {e.artifact_id: e for e in _extract_diagram_entities(diag)}
    ct = entities[f"{_GSN_ID}#nodes/g1"].content_text
    assert "g1" not in ct.split()  # node_id should not appear
    assert "The system is acceptably secure" in ct
    assert "goal" in ct


# ── unit: _diagram_local_to_full with node_id ────────────────────────────────


def test_local_to_full_resolves_node_id_items() -> None:
    diag = _make_gsn_diagram_record()
    mapping = _diagram_local_to_full(diag)
    assert mapping["g1"] == f"{_GSN_ID}#nodes/g1"
    assert mapping["s1"] == f"{_GSN_ID}#nodes/s1"
    assert mapping["cx1"] == f"{_GSN_ID}#nodes/cx1"


# ── unit: _extract_diagram_connections from diagram-entities.edges ────────────


def test_extract_gsn_connections_from_edges_sub_key() -> None:
    diag = _make_gsn_diagram_record()
    conns = _extract_diagram_connections(diag)
    assert len(conns) == 2
    conn_types = {c.conn_type for c in conns}
    assert "supported-by" in conn_types
    assert "in-context-of" in conn_types


def test_extract_gsn_connections_source_target_resolved() -> None:
    diag = _make_gsn_diagram_record()
    conns = _extract_diagram_connections(diag)
    sb = next(c for c in conns if c.conn_type == "supported-by")
    assert sb.source == f"{_GSN_ID}#nodes/g1"
    assert sb.target == f"{_GSN_ID}#nodes/s1"


def test_extract_gsn_connections_stable_artifact_id() -> None:
    diag = _make_gsn_diagram_record()
    conns = _extract_diagram_connections(diag)
    ids = {c.artifact_id for c in conns}
    # ID generated from source:conn_type:target (no explicit 'id' field)
    expected_sb = f"{_GSN_ID}#conn/g1:supported-by:s1"
    expected_ic = f"{_GSN_ID}#conn/g1:in-context-of:cx1"
    assert expected_sb in ids
    assert expected_ic in ids


# ── integration: read_artifact returns non-null for GSN node_id entities ─────


def test_read_artifact_non_null_for_gsn_node_id_entity(tmp_path: Path) -> None:
    """Regression: read_artifact must not return None for diagram-only nodes using node_id."""
    _write(tmp_path / _GSN_FILE, _GSN_DIAGRAM_CONTENT)
    store = shared_artifact_index(tmp_path)
    store.refresh()
    repo = ArtifactRepository(store)

    g1_id = f"{_GSN_ID}#nodes/g1"
    result = repo.read_artifact(g1_id, mode="full")
    assert result is not None, "read_artifact returned None for a GSN diagram-only node — contract broken"
    assert result["name"] == "The system is acceptably secure"
    assert result["host_diagram_id"] == _GSN_ID
    assert result["domain"] == "gsn"


def test_read_artifact_returns_none_for_unknown_id(tmp_path: Path) -> None:
    _write(tmp_path / _GSN_FILE, _GSN_DIAGRAM_CONTENT)
    store = shared_artifact_index(tmp_path)
    store.refresh()
    repo = ArtifactRepository(store)

    assert repo.read_artifact("GSN@0#nodes/nonexistent") is None


def test_gsn_nodes_appear_in_list_entities(tmp_path: Path) -> None:
    _write(tmp_path / _GSN_FILE, _GSN_DIAGRAM_CONTENT)
    store = shared_artifact_index(tmp_path)
    store.refresh()
    repo = ArtifactRepository(store)

    all_entities = repo.list_entities()
    gsn_entities = [e for e in all_entities if e.host_diagram_id == _GSN_ID]
    assert len(gsn_entities) == 3
    names = {e.name for e in gsn_entities}
    assert "The system is acceptably secure" in names


def test_gsn_connections_appear_in_list_connections(tmp_path: Path) -> None:
    _write(tmp_path / _GSN_FILE, _GSN_DIAGRAM_CONTENT)
    store = shared_artifact_index(tmp_path)
    store.refresh()
    repo = ArtifactRepository(store)

    all_conns = repo.list_connections()
    gsn_conns = [c for c in all_conns if c.artifact_id.startswith(_GSN_ID + "#conn/")]
    assert len(gsn_conns) == 2
    assert {c.conn_type for c in gsn_conns} == {"supported-by", "in-context-of"}


def test_gsn_entities_have_display_alias_matching_node_id(tmp_path: Path) -> None:
    _write(tmp_path / _GSN_FILE, _GSN_DIAGRAM_CONTENT)
    store = shared_artifact_index(tmp_path)
    store.refresh()
    repo = ArtifactRepository(store)

    entities = repo.list_entities()
    gsn_map = {e.artifact_id: e.display_alias for e in entities if e.host_diagram_id == _GSN_ID}
    assert gsn_map.get(f"{_GSN_ID}#nodes/g1") == "g1"
    assert gsn_map.get(f"{_GSN_ID}#nodes/cx1") == "cx1"
