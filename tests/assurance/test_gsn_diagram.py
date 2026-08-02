"""Tests for the GSN (Goal Structuring Notation) diagram type module."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

import pytest

from src.diagram_types.gsn import module as gsn_module
from src.domain.ontology_representation.ontology_protocol import NativeSvgDiagramRenderer


def test_module_name() -> None:
    assert str(gsn_module.name) == "gsn"


def test_module_class_is_architecture() -> None:
    assert gsn_module.module_class == "architecture"


def test_general_gsn_does_not_require_confidential_store() -> None:
    assert list(getattr(gsn_module, "requires", [])) == []


def test_accepts_no_entity_types() -> None:
    from src.domain.modules.module_types import EntityTypeName

    assert gsn_module.accepts_entity_type(EntityTypeName("application-component")) is False


def test_accepts_no_connection_types() -> None:
    from src.domain.modules.module_types import ConnectionTypeName

    assert gsn_module.accepts_connection_type(ConnectionTypeName("archimate-composition")) is False


def test_write_guidance_has_content() -> None:
    guidance = gsn_module.write_guidance()
    assert "gsn" in guidance.when_to_use.lower() or "goal" in guidance.when_to_use.lower()
    assert guidance.when_not_to_use


def test_renderer_empty_entities_produces_skeleton() -> None:
    renderer = gsn_module.renderer
    body = renderer.render_body("empty", [], [], "gsn", Path("/"))
    assert "@startuml" in body
    assert "@enduml" in body


def test_renderer_goal_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "G1", "name": "System is safe", "gsn_type": "goal"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test-gsn", [], [], "gsn", Path("/fake"), diagram_entities=diagram_entities
    )
    assert "@startuml" in body
    assert "@enduml" in body
    assert "G: System is safe" in body
    assert '$GsnGoal(G1, "G: System is safe")' in body
    assert "BackgroundColor<<GsnGoal>> #D0E8FF" in body


def test_renderer_strategy_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "S1", "name": "By hazard decomposition", "gsn_type": "strategy"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "S: By hazard decomposition" in body
    assert '$GsnStrategy(S1, "S: By hazard decomposition")' in body
    assert "card" not in body
    assert "BackgroundColor<<GsnStrategy>> #E8E0FF" in body


def test_renderer_solution_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "Sn1", "name": "Test Report T-001", "gsn_type": "solution"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert '$GsnSolution(Sn1, "Sn: Test Report\\nT-001")' in body
    assert "database" not in body
    assert "BackgroundColor<<GsnSolution>> #D0FFD8" in body


def test_renderer_context_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "C1", "name": "Safety concern", "gsn_type": "context"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "C: Safety concern" in body
    assert '$GsnContext(C1, "C: Safety concern")' in body
    assert "BackgroundColor<<GsnContext>> #FFFFD0" in body


def test_renderer_assumption_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "A1", "name": "Normal operation", "gsn_type": "assumption"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "A: Normal operation" in body
    assert '$GsnAssumption(A1, "A: Normal operation")' in body
    assert "BackgroundColor<<GsnAssumption>> #FFE8D0" in body


def test_renderer_justification_node() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [{"node_id": "J1", "name": "Industry standard", "gsn_type": "justification"}],
        "edges": [],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "J: Industry standard" in body
    assert '$GsnJustification(J1, "J: Industry standard")' in body
    assert "BackgroundColor<<GsnJustification>> #FFD0E8" in body


def test_renderer_undeveloped_marker() -> None:
    body = gsn_module.renderer.render_body(
        "test",
        [],
        [],
        "gsn",
        Path("/"),
        diagram_entities={
            "nodes": [{"node_id": "U1", "name": "Further argument required", "gsn_type": "undeveloped"}],
            "edges": [],
        },
    )
    assert '$GsnUndeveloped(U1, "Further argument required")' in body


def test_renderer_supported_by_edge() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
            {"node_id": "Sn1", "name": "Evidence", "gsn_type": "solution"},
        ],
        "edges": [{"source_id": "G1", "target_id": "Sn1", "conn_type": "supported-by"}],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "$GsnSupportedBy(G1, Sn1)" in body
    assert "$source --> $target : supported-by" in body


def test_renderer_in_context_of_edge_uses_hollow_arrowhead() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
            {"node_id": "C1", "name": "Context", "gsn_type": "context"},
        ],
        "edges": [{"source_id": "G1", "target_id": "C1", "conn_type": "in-context-of"}],
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "$GsnInContextOf(G1, C1)" in body
    assert "$source --|> $target : in-context-of" in body


def test_renderer_full_gsn_argument() -> None:
    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": [
            {"node_id": "G_TOP", "name": "System is acceptably safe", "gsn_type": "goal"},
            {"node_id": "S1", "name": "By hazard decomposition", "gsn_type": "strategy"},
            {"node_id": "G_H1", "name": "H1 is controlled", "gsn_type": "goal"},
            {"node_id": "Sn1", "name": "Test report", "gsn_type": "solution"},
            {"node_id": "C1", "name": "Safety context", "gsn_type": "context"},
        ],
        "edges": [
            {"source_id": "G_TOP", "target_id": "S1", "conn_type": "supported-by"},
            {"source_id": "S1", "target_id": "G_H1", "conn_type": "supported-by"},
            {"source_id": "G_H1", "target_id": "Sn1", "conn_type": "supported-by"},
            {"source_id": "G_TOP", "target_id": "C1", "conn_type": "in-context-of"},
        ],
    }
    body = renderer.render_body(
        "full-gsn", [], [], "gsn", Path("/fake"), diagram_entities=diagram_entities
    )
    assert "System is acceptably safe" in body
    assert "By hazard decomposition" in body
    assert "H1 is controlled" in body
    assert "Test report" in body
    assert "Safety context" in body
    assert "top to bottom direction" in body


def test_inject_includes_noop() -> None:
    body = gsn_module.renderer.inject_includes("@startuml\n@enduml", Path("/fake"))
    assert body == "@startuml\n@enduml"


def test_the_renderer_does_not_claim_to_discover_model_references() -> None:
    """This notation's diagram-owned data names no model artifact, and it says so by *not*
    implementing the capability.

    It used to be a required method returning an empty result — twelve of thirteen renderers had one,
    seven of them identical. `collect_references` is `ModelReferencingDiagramRenderer` now, and the
    single caller asks with `isinstance`, so "nothing to discover" is the absence of an implementation
    rather than four lines that delete their arguments."""
    from src.domain.ontology_representation.ontology_protocol import (
        ModelReferencingDiagramRenderer,
    )

    assert not isinstance(gsn_module.renderer, ModelReferencingDiagramRenderer)


def test_renderer_json_string_nodes() -> None:
    """diagram_entities nodes/edges can be JSON strings."""
    import json

    renderer = gsn_module.renderer
    diagram_entities = {
        "nodes": json.dumps([{"node_id": "G1", "name": "Claim", "gsn_type": "goal"}]),
        "edges": json.dumps([]),
    }
    body = renderer.render_body(
        "test", [], [], "gsn", Path("/"), diagram_entities=diagram_entities
    )
    assert "Claim" in body


def test_native_svg_uses_standard_shapes_and_accessibility() -> None:
    puml = gsn_module.renderer.render_body(
        "shapes",
        [],
        [],
        "gsn",
        Path("/"),
        diagram_entities={
            "nodes": [
                {"node_id": "S1", "name": "Strategy", "gsn_type": "strategy"},
                {"node_id": "Sn1", "name": "Evidence", "gsn_type": "solution"},
                {"node_id": "C1", "name": "Context", "gsn_type": "context"},
                {"node_id": "A1", "name": "Assumption", "gsn_type": "assumption"},
                {"node_id": "J1", "name": "Justification", "gsn_type": "justification"},
                {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
                {"node_id": "U1", "name": "Undeveloped", "gsn_type": "undeveloped"},
            ],
            "edges": [],
        },
    )
    result = cast(NativeSvgDiagramRenderer, gsn_module.renderer).render_svg(puml)
    root = ET.fromstring(result)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    groups = {
        alias: group
        for group in root.findall(".//svg:g", ns)
        if (alias := group.get("data-qualified-name")) is not None
    }
    assert groups["S1"].find("svg:polygon", ns) is not None
    solution = groups["Sn1"].find("svg:circle", ns)
    assert solution is not None
    context = groups["C1"].find("svg:rect", ns)
    assert context is not None
    rx, height = float(context.get("rx", "0")), float(context.get("height", "0"))
    assert 0 < rx < height / 2, "context must be a rounded rectangle, not a pill"
    assert groups["U1"].find("svg:polygon", ns) is not None
    assert groups["A1"].find("svg:ellipse", ns) is not None
    assert groups["J1"].find("svg:ellipse", ns) is not None
    assert groups["G1"].find("svg:rect", ns) is not None
    assert all(group.get("role") == "group" for group in groups.values())
    assert root.get("role") == "img"
    assert '#111827' in result


def test_generated_puml_fallback_is_valid(tmp_path: Path) -> None:
    from src.application.verification.artifact_verifier_syntax import check_puml_syntax

    body = gsn_module.renderer.render_body(
        "fallback",
        [],
        [],
        "gsn",
        tmp_path,
        diagram_entities={
            "nodes": [
                {"node_id": "G1", "name": "Claim", "gsn_type": "goal"},
                {"node_id": "S1", "name": "Argument", "gsn_type": "strategy"},
                {"node_id": "Sn1", "name": "Evidence", "gsn_type": "solution"},
                {"node_id": "C1", "name": "Context", "gsn_type": "context"},
                {"node_id": "A1", "name": "Assumption", "gsn_type": "assumption"},
                {"node_id": "J1", "name": "Justification", "gsn_type": "justification"},
                {"node_id": "U1", "name": "Undeveloped", "gsn_type": "undeveloped"},
            ],
            "edges": [
                {"source_id": "G1", "target_id": "S1", "conn_type": "supported-by"},
                {"source_id": "S1", "target_id": "Sn1", "conn_type": "supported-by"},
                {"source_id": "G1", "target_id": "C1", "conn_type": "in-context-of"},
            ],
        },
    )
    path = tmp_path / "fallback.puml"
    path.write_text(body, encoding="utf-8")
    assert check_puml_syntax(path, str(path)) == []


def test_native_renderer_migrates_stored_legacy_gsn_source() -> None:
    legacy = """\
@startuml legacy
usecase "C: Scope" as cx1 #FFFFD0
rectangle "G: Protected" as g1 #D0E8FF
card "S: Argue over controls" as s1 #E8E0FF
database "Sn: Verification report" as sn1 #D0FFD8
g1 ..> cx1 : in-context-of
g1 --> s1 : supported-by
s1 --> sn1 : supported-by
@enduml
"""
    svg = cast(NativeSvgDiagramRenderer, gsn_module.renderer).render_svg(legacy)
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    groups = {
        alias: group
        for group in root.findall(".//svg:g", ns)
        if (alias := group.get("data-qualified-name")) is not None
    }
    assert groups["s1"].find("svg:polygon", ns) is not None
    assert groups["sn1"].find("svg:circle", ns) is not None
    assert groups["cx1"].find("svg:rect", ns).get("rx") is not None  # type: ignore[union-attr]
    assert 'marker-end="url(#gsn-hollow-arrow)"' in svg


def test_rendered_svg_retains_click_targets_and_gsn_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.rendering.diagram_builder import render_puml_preview, render_puml_svg

    monkeypatch.setattr(
        "src.infrastructure.rendering.puml_runtime.get_diagram_type", lambda _name: gsn_module
    )
    monkeypatch.setattr(
        "src.infrastructure.rendering.native_svg.find_diagram_type",
        lambda _name: gsn_module,
    )
    (tmp_path / "diagram-catalog" / "diagrams").mkdir(parents=True)
    body = gsn_module.renderer.render_body(
        "rendered-gsn",
        [],
        [],
        "gsn",
        tmp_path,
        diagram_entities={
            "nodes": [
                {"node_id": "S1", "name": "Argument", "gsn_type": "strategy"},
                {"node_id": "Sn1", "name": "Verification report", "gsn_type": "solution"},
                {"node_id": "C1", "name": "Operating context", "gsn_type": "context"},
            ],
            "edges": [
                {"source_id": "S1", "target_id": "Sn1", "conn_type": "supported-by"},
                {"source_id": "S1", "target_id": "C1", "conn_type": "in-context-of"},
            ],
        },
    )
    svg, warnings = render_puml_svg(body, tmp_path, "gsn")
    assert warnings == []
    assert svg is not None
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    groups = {
        alias: group
        for group in root.findall(".//svg:g", ns)
        if (alias := group.get("data-qualified-name")) is not None
    }
    assert {"S1", "Sn1", "C1"} <= groups.keys()
    assert groups["S1"].find("svg:polygon", ns) is not None
    assert groups["Sn1"].find("svg:circle", ns) is not None
    assert groups["C1"].find("svg:rect", ns).get("rx") is not None  # type: ignore[union-attr]
    assert all(group.get("data-gsn-type") for group in groups.values())
    assert 'marker-end="url(#gsn-filled-arrow)"' in svg
    assert 'marker-end="url(#gsn-hollow-arrow)"' in svg
    preview, preview_warnings = render_puml_preview(body, tmp_path, "gsn")
    assert preview_warnings == []
    assert preview is not None and preview.startswith("data:image/svg+xml;base64,")
