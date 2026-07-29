"""Tests for the control-structure diagram type (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from src.diagram_types.control_structure import module as cs_module


def test_module_name() -> None:
    assert str(cs_module.name) == "control-structure"


def test_module_class_is_assurance() -> None:
    assert cs_module.module_class == "assurance"


def test_requires_confidential_store() -> None:
    requires = list(getattr(cs_module, "requires", []))
    assert "confidential_store" in requires


def test_accepts_no_entity_types() -> None:
    from src.domain.modules.module_types import EntityTypeName

    assert cs_module.accepts_entity_type(EntityTypeName("application-component")) is False


def test_accepts_no_connection_types() -> None:
    from src.domain.modules.module_types import ConnectionTypeName

    assert cs_module.accepts_connection_type(ConnectionTypeName("archimate-composition")) is False


def test_renderer_produces_valid_puml() -> None:
    renderer = cs_module.renderer
    diagram_entities = {
        "nodes": [
            {
                "node_id": "CSN@001",
                "name": "ECU",
                "node_type": "control-structure-node",
                "binding_status": "bound",
                "node_role": "controller",
            },
            {
                "node_id": "CTA@001",
                "name": "Throttle Command",
                "node_type": "control-action",
                "binding_status": "unbound-pending",
                "node_role": "",
            },
        ],
        "edges": [
            {"source_id": "CSN@001", "target_id": "CTA@001", "conn_type": "issues"},
        ],
    }
    body = renderer.render_body(
        "test-cs",
        [],
        [],
        "control-structure",
        Path("/fake"),
        diagram_entities=diagram_entities,
    )
    assert "@startuml" in body
    assert "@enduml" in body
    assert "ECU" in body
    assert "Throttle Command" in body
    assert "[?]" in body
    assert "<<controller>>" in body


def test_renderer_bound_node_no_marker() -> None:
    renderer = cs_module.renderer
    diagram_entities = {
        "nodes": [
            {
                "node_id": "CSN@002",
                "name": "Sensor",
                "node_type": "control-structure-node",
                "binding_status": "bound",
                "node_role": "sensor",
            }
        ],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "control-structure", Path("/"), diagram_entities=diagram_entities
    )
    assert "[?]" not in body
    assert "[~]" not in body
    assert "<<sensor>>" in body


def test_renderer_out_of_scope_marker() -> None:
    renderer = cs_module.renderer
    diagram_entities = {
        "nodes": [
            {
                "node_id": "CSN@003",
                "name": "External System",
                "node_type": "control-structure-node",
                "binding_status": "out-of-scope",
                "node_role": "",
            }
        ],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "control-structure", Path("/"), diagram_entities=diagram_entities
    )
    assert "[~]" in body


def test_renderer_feedback_edge_uses_dotted_arrow() -> None:
    renderer = cs_module.renderer
    diagram_entities = {
        "nodes": [
            {
                "node_id": "CSN@A",
                "name": "A",
                "node_type": "control-structure-node",
                "binding_status": "bound",
                "node_role": "",
            },
            {
                "node_id": "CSN@B",
                "name": "B",
                "node_type": "control-structure-node",
                "binding_status": "bound",
                "node_role": "",
            },
        ],
        "edges": [
            {"source_id": "CSN@A", "target_id": "CSN@B", "conn_type": "feedback"},
        ],
    }
    body = renderer.render_body(
        "test", [], [], "control-structure", Path("/"), diagram_entities=diagram_entities
    )
    assert "..>" in body


def test_renderer_empty_entities_produces_skeleton() -> None:
    renderer = cs_module.renderer
    body = renderer.render_body("empty", [], [], "control-structure", Path("/"))
    assert "@startuml" in body
    assert "@enduml" in body


def test_inject_includes_noop() -> None:
    body = cs_module.renderer.inject_includes("@startuml\n@enduml", Path("/fake"))
    assert body == "@startuml\n@enduml"


def test_collect_references_returns_empty() -> None:
    from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences

    result = cs_module.renderer.collect_references("control-structure", Path("/fake"))
    assert isinstance(result, DiagramRendererReferences)
