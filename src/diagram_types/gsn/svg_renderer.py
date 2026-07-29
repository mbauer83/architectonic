"""Native SVG renderer for GSN Community Standard notation."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from dataclasses import dataclass

_NODE_CALL = re.compile(
    r'^\$(GsnGoal|GsnStrategy|GsnSolution|GsnContext|GsnAssumption|'
    r'GsnJustification|GsnUndeveloped)\(([A-Za-z0-9_]+),\s*"((?:\\.|[^"])*)"\)',
    re.MULTILINE,
)
_EDGE_CALL = re.compile(
    r"^\$(GsnSupportedBy|GsnInContextOf)\(([A-Za-z0-9_]+),\s*([A-Za-z0-9_]+)\)",
    re.MULTILINE,
)
_LEGACY_NODE = re.compile(
    r'^(rectangle|card|database|usecase)\s+"((?:\\.|[^"])*)"\s+as\s+([A-Za-z0-9_]+)',
    re.MULTILINE,
)
_LEGACY_EDGE = re.compile(
    r"^([A-Za-z0-9_]+)\s+(?:-->|\.\.>|--\|>)\s+([A-Za-z0-9_]+)\s*:\s*"
    r"(supported-by|in-context-of)",
    re.MULTILINE,
)
_TYPE_BY_PROCEDURE = {
    "GsnGoal": "goal",
    "GsnStrategy": "strategy",
    "GsnSolution": "solution",
    "GsnContext": "context",
    "GsnAssumption": "assumption",
    "GsnJustification": "justification",
    "GsnUndeveloped": "undeveloped",
}
_EDGE_BY_PROCEDURE = {
    "GsnSupportedBy": "supported-by",
    "GsnInContextOf": "in-context-of",
}
_FILL = {
    "goal": "#D0E8FF",
    "strategy": "#E8E0FF",
    "solution": "#D0FFD8",
    "context": "#FFFFD0",
    "assumption": "#FFE8D0",
    "justification": "#FFD0E8",
    "undeveloped": "#FFFFFF",
}
_LEGEND_LABEL = {
    "goal": "Goal",
    "strategy": "Strategy",
    "solution": "Solution",
    "context": "Context",
    "assumption": "Assumption",
    "justification": "Justification",
    "undeveloped": "Undeveloped",
}


@dataclass(frozen=True)
class GsnNode:
    alias: str
    node_type: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class GsnEdge:
    source: str
    target: str
    edge_type: str


@dataclass(frozen=True)
class PlacedNode:
    node: GsnNode
    x: float
    y: float
    width: float
    height: float


def _unescape_label(value: str) -> tuple[str, ...]:
    text = value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return tuple(text.splitlines()) or ("",)


def _parse(puml_body: str) -> tuple[list[GsnNode], list[GsnEdge]]:
    nodes = [
        GsnNode(alias, _TYPE_BY_PROCEDURE[procedure], _unescape_label(label))
        for procedure, alias, label in _NODE_CALL.findall(puml_body)
    ]
    edges = [
        GsnEdge(source, target, _EDGE_BY_PROCEDURE[procedure])
        for procedure, source, target in _EDGE_CALL.findall(puml_body)
    ]
    if nodes:
        return nodes, edges
    nodes = [
        GsnNode(alias, _legacy_type(shape, label), _unescape_label(label))
        for shape, label, alias in _LEGACY_NODE.findall(puml_body)
    ]
    edges = [
        GsnEdge(source, target, edge_type)
        for source, target, edge_type in _LEGACY_EDGE.findall(puml_body)
    ]
    return nodes, edges


def _legacy_type(shape: str, label: str) -> str:
    prefix = label.lstrip().split(":", 1)[0].lower()
    return {
        "g": "goal",
        "s": "strategy",
        "sn": "solution",
        "c": "context",
        "a": "assumption",
        "j": "justification",
    }.get(prefix, {"card": "strategy", "database": "solution", "usecase": "context"}.get(shape, "goal"))


def _node_size(node: GsnNode) -> tuple[float, float]:
    longest = max((len(line) for line in node.lines), default=1)
    text_width = longest * 7.4
    text_height = max(1, len(node.lines)) * 18
    if node.node_type == "solution":
        diameter = max(94.0, text_width + 30, text_height + 34)
        return diameter, diameter
    if node.node_type == "undeveloped":
        return 34.0, 34.0
    width = max(130.0, text_width + 34)
    height = max(54.0, text_height + 26)
    if node.node_type in {"assumption", "justification"}:
        width = max(width, height * 2.3)
    return width, height


def _depths(nodes: list[GsnNode], edges: list[GsnEdge]) -> dict[str, int]:
    aliases = {node.alias for node in nodes}
    incoming = {alias: 0 for alias in aliases}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.edge_type != "supported-by" or edge.source not in aliases or edge.target not in aliases:
            continue
        incoming[edge.target] += 1
        children[edge.source].append(edge.target)
    depths = {alias: 0 for alias, count in incoming.items() if count == 0}
    queue = list(depths)
    while queue:
        source = queue.pop(0)
        for target in children[source]:
            if target not in depths:
                depths[target] = depths[source] + 1
                queue.append(target)
    return {alias: depths.get(alias, 0) for alias in aliases}


def _place(nodes: list[GsnNode], edges: list[GsnEdge]) -> tuple[list[PlacedNode], float, float]:
    depths = _depths(nodes, edges)
    for edge in edges:
        if edge.edge_type == "in-context-of" and edge.source in depths and edge.target in depths:
            depths[edge.target] = depths[edge.source]
    context_targets = {
        edge.target for edge in edges if edge.edge_type == "in-context-of" and edge.target in depths
    }
    layers: dict[int, list[GsnNode]] = defaultdict(list)
    side_nodes: list[GsnNode] = []
    for node in nodes:
        (side_nodes if node.alias in context_targets else layers[depths[node.alias]]).append(node)

    horizontal_gap, vertical_gap, margin = 54.0, 84.0, 40.0
    layer_widths = [
        sum(_node_size(node)[0] for node in layer) + horizontal_gap * max(0, len(layer) - 1)
        for _, layer in sorted(layers.items())
    ]
    main_width = max(layer_widths, default=200.0)
    side_width = max((_node_size(node)[0] for node in side_nodes), default=0.0)
    canvas_width = margin * 2 + main_width + (horizontal_gap + side_width if side_nodes else 0)

    placed: list[PlacedNode] = []
    y = margin
    layer_y: dict[int, float] = {}
    for depth, layer in sorted(layers.items()):
        sizes = [_node_size(node) for node in layer]
        layer_height = max((height for _, height in sizes), default=54.0)
        total_width = sum(width for width, _ in sizes) + horizontal_gap * max(0, len(layer) - 1)
        x = margin + (main_width - total_width) / 2
        layer_y[depth] = y + layer_height / 2
        for node, (width, height) in zip(layer, sizes, strict=True):
            placed.append(PlacedNode(node, x + width / 2, y + layer_height / 2, width, height))
            x += width + horizontal_gap
        y += layer_height + vertical_gap

    side_counts: dict[int, int] = defaultdict(int)
    side_x = margin + main_width + horizontal_gap
    for node in side_nodes:
        depth = depths[node.alias]
        width, height = _node_size(node)
        offset = side_counts[depth] * (height + 18)
        placed.append(PlacedNode(node, side_x + width / 2, layer_y.get(depth, margin) + offset, width, height))
        side_counts[depth] += 1
    canvas_height = max((node.y + node.height / 2 for node in placed), default=80.0) + margin
    return placed, canvas_width, canvas_height


def _shape(item: PlacedNode) -> str:
    node, x, y, width, height = item.node, item.x, item.y, item.width, item.height
    left, top = x - width / 2, y - height / 2
    style = f'fill="{_FILL[node.node_type]}" stroke="#20242A" stroke-width="1.5"'
    if node.node_type == "strategy":
        skew = min(22.0, width / 5)
        points = f"{left + skew},{top} {left + width},{top} {left + width - skew},{top + height} {left},{top + height}"
        return f'<polygon points="{points}" {style}/>'
    if node.node_type == "solution":
        return f'<circle cx="{x}" cy="{y}" r="{width / 2}" {style}/>'
    if node.node_type in {"assumption", "justification"}:
        return f'<ellipse cx="{x}" cy="{y}" rx="{width / 2}" ry="{height / 2}" {style}/>'
    if node.node_type == "context":
        return f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="10" {style}/>'
    if node.node_type == "undeveloped":
        points = f"{x},{top} {left + width},{y} {x},{top + height} {left},{y}"
        return f'<polygon points="{points}" {style}/>'
    return f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="3" {style}/>'


def _text(item: PlacedNode) -> str:
    if item.node.node_type == "undeveloped":
        return ""
    start_y = item.y - (len(item.node.lines) - 1) * 9 + 5
    spans = "".join(
        f'<tspan x="{item.x}" y="{start_y + index * 18}">{html.escape(line)}</tspan>'
        for index, line in enumerate(item.node.lines)
    )
    return f'<text text-anchor="middle" font-family="sans-serif" font-size="14" fill="#111827">{spans}</text>'


def _edge(edge: GsnEdge, by_alias: dict[str, PlacedNode]) -> str:
    source, target = by_alias.get(edge.source), by_alias.get(edge.target)
    if source is None or target is None:
        return ""
    horizontal = edge.edge_type == "in-context-of"
    if horizontal:
        direction = 1 if target.x >= source.x else -1
        x1, y1 = source.x + direction * source.width / 2, source.y
        x2, y2 = target.x - direction * target.width / 2, target.y
        marker = "url(#gsn-hollow-arrow)"
    else:
        direction = 1 if target.y >= source.y else -1
        x1, y1 = source.x, source.y + direction * source.height / 2
        x2, y2 = target.x, target.y - direction * target.height / 2
        marker = "url(#gsn-filled-arrow)"
    return (
        f'<g class="link" data-entity-1="{html.escape(edge.source)}" '
        f'data-entity-2="{html.escape(edge.target)}" data-gsn-edge="{edge.edge_type}">'
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#20242A" '
        f'stroke-width="1.5" marker-end="{marker}"/></g>'
    )


def _legend(present_types: list[str], top: float, left: float) -> tuple[str, float]:
    """Compact legend row: a swatch + label per node kind actually present in the diagram."""
    chip, gap_after_chip, gap_between = 14.0, 6.0, 24.0
    x = left
    parts = []
    for node_type in present_types:
        label = _LEGEND_LABEL[node_type]
        parts.append(
            f'<rect x="{x}" y="{top}" width="{chip}" height="{chip}" rx="2" '
            f'fill="{_FILL[node_type]}" stroke="#20242A" stroke-width="1"/>'
            f'<text x="{x + chip + gap_after_chip}" y="{top + chip - 2}" '
            f'font-family="sans-serif" font-size="12" fill="#111827">{html.escape(label)}</text>'
        )
        x += chip + gap_after_chip + len(label) * 6.5 + gap_between
    return "".join(parts), x - gap_between if present_types else left


def render_gsn_svg(puml_body: str) -> str:
    nodes, edges = _parse(puml_body)
    placed, width, height = _place(nodes, edges)
    by_alias = {item.node.alias: item for item in placed}
    edge_markup = "".join(_edge(edge, by_alias) for edge in edges)
    node_markup = "".join(
        f'<g class="entity" id="entity_{html.escape(item.node.alias)}" '
        f'data-qualified-name="{html.escape(item.node.alias)}" '
        f'data-gsn-type="{item.node.node_type}" role="group" '
        f'aria-label="{html.escape(" ".join(item.node.lines))}">'
        f'<title>{html.escape(" ".join(item.node.lines))}</title>{_shape(item)}{_text(item)}</g>'
        for item in placed
    )
    present_types = [node_type for node_type in _FILL if any(node.node_type == node_type for node in nodes)]
    legend_margin = 16.0
    legend_markup, legend_right = _legend(present_types, height + 14.0, legend_margin)
    legend_height = 40.0 if present_types else 0.0
    total_width = max(width, legend_right + legend_margin)
    total_height = height + legend_height
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{total_height}" '
        f'viewBox="0 0 {total_width} {total_height}" role="img" '
        'aria-label="Goal Structuring Notation diagram">'
        "<defs>"
        '<marker id="gsn-filled-arrow" markerWidth="13" markerHeight="13" refX="11" refY="4" '
        'orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,8 L11,4 z" fill="#20242A"/></marker>'
        '<marker id="gsn-hollow-arrow" markerWidth="14" markerHeight="14" refX="12" refY="5" '
        'orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,10 L12,5 z" fill="#FFFFFF" '
        'stroke="#20242A" stroke-width="1"/></marker>'
        "</defs>"
        f'{edge_markup}{node_markup}<g class="legend">{legend_markup}</g></svg>'
    )
