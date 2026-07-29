"""Rendered-SVG assertion harness for GSN diagrams (T23).

Uses the native render_gsn_svg renderer (no PlantUML required) to produce
SVG from GSN PUML bodies and asserts that:
  - node label text is present in the SVG for every node type
  - each node type maps to the correct SVG shape element
  - edge lines are rendered between nodes

Shape expectations from svg_renderer.py:
  goal          → <rect rx="3">
  strategy      → <polygon> (parallelogram)
  solution      → <circle>
  context       → <rect rx="10"> (rounded rectangle, GSN Community Standard notation)
  assumption    → <ellipse>
  justification → <ellipse>
  undeveloped   → <polygon> (diamond)

This file is the GSN counterpart of test_c4_rendered_svg.py.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from src.diagram_types.gsn.renderer import render_gsn
from src.diagram_types.gsn.svg_renderer import render_gsn_svg

_NS = {"svg": "http://www.w3.org/2000/svg"}


# ── harness helpers ────────────────────────────────────────────────────────────

def _render(
    nodes: list[dict],
    edges: list[dict] | None = None,
    name: str = "test",
) -> str:
    """Render GSN nodes+edges to SVG via the full renderer pipeline."""
    puml = render_gsn(name, nodes, edges or [])
    return render_gsn_svg(puml)


def _groups(svg: str) -> dict[str, ET.Element]:
    root = ET.fromstring(svg)
    return {
        alias: g
        for g in root.findall(".//svg:g", _NS)
        if (alias := g.get("data-qualified-name")) is not None
    }


def _node(nodes: list[dict], edges: list[dict] | None = None, name: str = "test") -> ET.Element:
    """Render a single node; return its SVG group element."""
    svg = _render(nodes, edges, name)
    alias = re.sub(r"[^A-Za-z0-9_]", "_", nodes[0]["node_id"])
    return _groups(svg)[alias]


# ── label text tests ───────────────────────────────────────────────────────────

def test_goal_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "G1", "name": "System safety case", "gsn_type": "goal"}])
    assert "System safety case" in svg


def test_strategy_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "S1", "name": "Argue over hazards", "gsn_type": "strategy"}])
    assert "Argue over hazards" in svg


def test_solution_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "Sn1", "name": "Test report 42", "gsn_type": "solution"}])
    assert "Test report 42" in svg


def test_context_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "C1", "name": "Operational scope", "gsn_type": "context"}])
    assert "Operational scope" in svg


def test_assumption_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "A1", "name": "No adversarial input", "gsn_type": "assumption"}])
    assert "No adversarial input" in svg


def test_justification_label_appears_in_svg() -> None:
    svg = _render([{"node_id": "J1", "name": "Per ISO 26262", "gsn_type": "justification"}])
    assert "Per ISO 26262" in svg


def test_undeveloped_label_absent_from_svg_text() -> None:
    """Undeveloped node has no text element — it renders as a bare diamond shape."""
    svg = _render([{"node_id": "U1", "name": "TBD", "gsn_type": "undeveloped"}])
    groups = _groups(svg)
    text_el = groups["U1"].find("svg:text", _NS)
    assert text_el is None, "Undeveloped node must not render a text element"


# ── shape element tests ────────────────────────────────────────────────────────

def test_goal_uses_rect_shape() -> None:
    group = _node([{"node_id": "G1", "name": "Goal", "gsn_type": "goal"}])
    assert group.find("svg:rect", _NS) is not None, "goal must render as <rect>"


def test_strategy_uses_polygon_shape() -> None:
    group = _node([{"node_id": "S1", "name": "Strategy", "gsn_type": "strategy"}])
    assert group.find("svg:polygon", _NS) is not None, "strategy must render as <polygon>"


def test_solution_uses_circle_shape() -> None:
    group = _node([{"node_id": "Sn1", "name": "Solution", "gsn_type": "solution"}])
    assert group.find("svg:circle", _NS) is not None, "solution must render as <circle>"


def test_context_uses_rounded_rect_shape() -> None:
    """GSN Community Standard renders context as a rounded rectangle, not a full pill."""
    group = _node([{"node_id": "C1", "name": "Context", "gsn_type": "context"}])
    rect = group.find("svg:rect", _NS)
    assert rect is not None, "context must render as <rect>"
    rx = float(rect.get("rx", "0"))
    height = float(rect.get("height", "0"))
    assert 0 < rx < height / 2, (
        f"context rect rx ({rx}) must be a modest corner radius, not a pill (height {height})"
    )


def test_assumption_uses_ellipse_shape() -> None:
    group = _node([{"node_id": "A1", "name": "Assumption", "gsn_type": "assumption"}])
    assert group.find("svg:ellipse", _NS) is not None, "assumption must render as <ellipse>"


def test_justification_uses_ellipse_shape() -> None:
    group = _node([{"node_id": "J1", "name": "Justification", "gsn_type": "justification"}])
    assert group.find("svg:ellipse", _NS) is not None, "justification must render as <ellipse>"


def test_undeveloped_uses_diamond_polygon() -> None:
    group = _node([{"node_id": "U1", "name": "TBD", "gsn_type": "undeveloped"}])
    assert group.find("svg:polygon", _NS) is not None, "undeveloped must render as <polygon>"


# ── edge tests ─────────────────────────────────────────────────────────────────

def test_supported_by_edge_renders_line() -> None:
    svg = _render(
        nodes=[
            {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
            {"node_id": "S1", "name": "Strategy", "gsn_type": "strategy"},
        ],
        edges=[{"source_id": "G1", "target_id": "S1", "conn_type": "supported-by"}],
    )
    assert '<line' in svg, "supported-by edge must produce a <line> element"
    assert 'data-gsn-edge="supported-by"' in svg


def test_in_context_of_edge_renders_hollow_arrow() -> None:
    svg = _render(
        nodes=[
            {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
            {"node_id": "C1", "name": "Context", "gsn_type": "context"},
        ],
        edges=[{"source_id": "G1", "target_id": "C1", "conn_type": "in-context-of"}],
    )
    assert 'gsn-hollow-arrow' in svg, "in-context-of edge must use the hollow arrowhead marker"
    assert 'data-gsn-edge="in-context-of"' in svg


# ── marker + legend tests ──────────────────────────────────────────────────────

def test_arrow_markers_use_user_space_on_use() -> None:
    """Marker size must be absolute (userSpaceOnUse), not scaled by a consumer's stroke-width —
    defense-in-depth against hit-area clones that copy a widened stroke-width."""
    svg = _render(
        nodes=[
            {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
            {"node_id": "S1", "name": "Strategy", "gsn_type": "strategy"},
        ],
        edges=[{"source_id": "G1", "target_id": "S1", "conn_type": "supported-by"}],
    )
    markers = re.findall(r'<marker[^>]*>', svg)
    assert markers, "expected marker definitions in <defs>"
    for marker in markers:
        assert 'markerUnits="userSpaceOnUse"' in marker


def test_legend_lists_exactly_the_kinds_present() -> None:
    nodes = [
        {"node_id": "G1", "name": "Goal", "gsn_type": "goal"},
        {"node_id": "S1", "name": "Strategy", "gsn_type": "strategy"},
        {"node_id": "Sn1", "name": "Solution", "gsn_type": "solution"},
    ]
    svg = _render(nodes)
    root = ET.fromstring(svg)
    legend = root.find(".//svg:g[@class='legend']", _NS)
    assert legend is not None
    labels = {text.text for text in legend.findall("svg:text", _NS)}
    assert labels == {"Goal", "Strategy", "Solution"}


def test_legend_omits_kinds_not_present() -> None:
    svg = _render([{"node_id": "G1", "name": "Goal", "gsn_type": "goal"}])
    root = ET.fromstring(svg)
    legend = root.find(".//svg:g[@class='legend']", _NS)
    assert legend is not None
    labels = [text.text for text in legend.findall("svg:text", _NS)]
    assert labels == ["Goal"]


def test_multi_node_diagram_labels_and_edges() -> None:
    """Integration: goal→strategy→solution with a context node; all labels + edges present."""
    nodes = [
        {"node_id": "G1", "name": "Safety2026", "gsn_type": "goal"},
        {"node_id": "S1", "name": "Strategy2026", "gsn_type": "strategy"},
        {"node_id": "Sn1", "name": "Evidence2026", "gsn_type": "solution"},
        {"node_id": "C1", "name": "Scope2026", "gsn_type": "context"},
    ]
    edges = [
        {"source_id": "G1", "target_id": "S1", "conn_type": "supported-by"},
        {"source_id": "S1", "target_id": "Sn1", "conn_type": "supported-by"},
        {"source_id": "G1", "target_id": "C1", "conn_type": "in-context-of"},
    ]
    svg = _render(nodes, edges)
    for label in ("Safety2026", "Strategy2026", "Evidence2026", "Scope2026"):
        assert label in svg, f"Label '{label}' missing from multi-node GSN SVG"
    assert svg.count("<line") >= 3, "Expected ≥3 edge lines for 3 connections"
