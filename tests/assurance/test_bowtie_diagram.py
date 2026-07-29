"""Tests for the bowtie diagram type module."""

from __future__ import annotations

from pathlib import Path

from src.diagram_types._assurance_puml_alias import safe_alias
from src.diagram_types.bowtie import module as bowtie_module


def test_module_name() -> None:
    assert str(bowtie_module.name) == "bowtie"


def test_module_class_is_assurance() -> None:
    assert bowtie_module.module_class == "assurance"


def test_requires_confidential_store() -> None:
    requires = list(getattr(bowtie_module, "requires", []))
    assert "confidential_store" in requires


def test_accepts_no_entity_types() -> None:
    from src.domain.modules.module_types import EntityTypeName

    assert bowtie_module.accepts_entity_type(EntityTypeName("application-component")) is False


def test_accepts_no_connection_types() -> None:
    from src.domain.modules.module_types import ConnectionTypeName

    assert bowtie_module.accepts_connection_type(ConnectionTypeName("archimate-composition")) is False


def test_write_guidance_has_content() -> None:
    guidance = bowtie_module.write_guidance()
    assert "bowtie" in guidance.when_to_use.lower() or "threat" in guidance.when_to_use.lower()
    assert guidance.when_not_to_use


def test_renderer_empty_entities_produces_skeleton() -> None:
    renderer = bowtie_module.renderer
    body = renderer.render_body("empty", [], [], "bowtie", Path("/"))
    assert "@startuml" in body
    assert "@enduml" in body


def test_renderer_produces_valid_puml_with_full_bowtie() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "T1", "name": "Cyber Attack", "role": "threat"},
            {"node_id": "BL1", "name": "Firewall", "role": "barrier_left"},
            {"node_id": "TE1", "name": "Unauthorised Access", "role": "top_event"},
            {"node_id": "BR1", "name": "Audit Log", "role": "barrier_right"},
            {"node_id": "C1", "name": "Data Breach", "role": "consequence"},
        ],
        "edges": [
            {"source_id": "T1", "target_id": "BL1", "label": "blocked by"},
            {"source_id": "BL1", "target_id": "TE1", "label": ""},
            {"source_id": "TE1", "target_id": "BR1", "label": "mitigated by"},
            {"source_id": "BR1", "target_id": "C1", "label": ""},
        ],
    }
    body = renderer.render_body(
        "test-bowtie",
        [],
        [],
        "bowtie",
        Path("/fake"),
        diagram_entities=diagram_entities,
    )
    assert "@startuml" in body
    assert "@enduml" in body
    assert "Cyber Attack" in body
    assert "Unauthorised Access" in body
    assert "Data Breach" in body
    assert "Firewall" in body
    assert "Audit Log" in body
    assert "<<threat>>" in body
    assert "<<top-event>>" in body
    assert "<<barrier>>" in body
    assert "<<consequence>>" in body


def test_renderer_threat_gets_red_colour() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "T1", "name": "Threat Node", "role": "threat"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    assert "#FFD0D0" in body


def test_renderer_top_event_gets_orange_colour() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "TE1", "name": "Top Event", "role": "top_event"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    assert "#FFB060" in body


def test_renderer_barrier_gets_green_colour() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "B1", "name": "Barrier", "role": "barrier_left"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    assert "#D0FFD0" in body


def test_renderer_edge_with_label() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "A", "name": "A", "role": "threat"},
            {"node_id": "B", "name": "B", "role": "consequence"},
        ],
        "edges": [{"source_id": "A", "target_id": "B", "label": "causes"}],
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    assert ': "causes"' in body


def test_renderer_edge_without_label() -> None:
    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "A", "name": "A", "role": "threat"},
            {"node_id": "B", "name": "B", "role": "consequence"},
        ],
        "edges": [{"source_id": "A", "target_id": "B", "label": ""}],
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    drawn = f'{safe_alias("A")} --> {safe_alias("B")}'
    assert drawn in body
    assert ": " not in body.split(drawn)[1].split("\n")[0]


def test_inject_includes_noop() -> None:
    body = bowtie_module.renderer.inject_includes("@startuml\n@enduml", Path("/fake"))
    assert body == "@startuml\n@enduml"


def test_collect_references_returns_empty() -> None:
    from src.domain.ontology_representation.ontology_protocol import DiagramRendererReferences

    result = bowtie_module.renderer.collect_references("bowtie", Path("/fake"))
    assert isinstance(result, DiagramRendererReferences)


def test_renderer_json_string_nodes() -> None:
    """diagram_entities nodes/edges can be JSON strings."""
    import json

    renderer = bowtie_module.renderer
    diagram_entities = {
        "nodes": json.dumps([{"node_id": "T1", "name": "Threat", "role": "threat"}]),
        "edges": json.dumps([]),
    }
    body = renderer.render_body(
        "test", [], [], "bowtie", Path("/"), diagram_entities=diagram_entities
    )
    assert "Threat" in body
