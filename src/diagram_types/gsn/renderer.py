"""Dedicated GSN renderer backed by reusable notation procedures."""

from __future__ import annotations

import json
import re
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types.gsn.svg_renderer import render_gsn_svg
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

_NOTATION = (Path(__file__).parent / "notation.puml").read_text(encoding="utf-8").strip()

_NODE_PROCEDURE = {
    "goal": ("GsnGoal", "G: "),
    "strategy": ("GsnStrategy", "S: "),
    "solution": ("GsnSolution", "Sn: "),
    "context": ("GsnContext", "C: "),
    "assumption": ("GsnAssumption", "A: "),
    "justification": ("GsnJustification", "J: "),
    "undeveloped": ("GsnUndeveloped", ""),
}
_DEFAULT_NODE_PROCEDURE = _NODE_PROCEDURE["goal"]
_EDGE_PROCEDURE = {
    "supported-by": "GsnSupportedBy",
    "in-context-of": "GsnInContextOf",
}


def _safe_alias(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", value)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "node"


def _items(value: object) -> list[dict[str, Any]]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _quoted_label(label: str, *, wrap: int = 38) -> str:
    normalized = " ".join(label.split())
    wrapped = textwrap.wrap(normalized, width=wrap, break_long_words=False) or [""]
    escaped = "\\n".join(line.replace("\\", "\\\\").replace('"', '\\"') for line in wrapped)
    return f'"{escaped}"'


def _node_line(node: Mapping[str, Any]) -> str:
    node_id = str(node.get("node_id", ""))
    node_type = str(node.get("gsn_type") or "goal")
    procedure, prefix = _NODE_PROCEDURE.get(node_type, _DEFAULT_NODE_PROCEDURE)
    name = str(node.get("name", node_id))
    wrap = 20 if node_type == "solution" else 38
    return f"${procedure}({_safe_alias(node_id)}, {_quoted_label(prefix + name, wrap=wrap)})"


def _edge_line(edge: Mapping[str, Any]) -> str:
    source = _safe_alias(str(edge.get("source_id", "")))
    target = _safe_alias(str(edge.get("target_id", "")))
    conn_type = str(edge.get("conn_type") or "supported-by")
    procedure = _EDGE_PROCEDURE.get(conn_type, "GsnSupportedBy")
    return f"${procedure}({source}, {target})"


def render_gsn(name: str, nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        f"@startuml {_safe_alias(name)}",
        "top to bottom direction",
        _NOTATION,
        "",
        *(_node_line(node) for node in nodes),
    ]
    if nodes and edges:
        lines.append("")
    lines.extend(_edge_line(edge) for edge in edges)
    lines.extend(["", "@enduml"])
    return "\n".join(lines)


class GsnDiagramRenderer:
    def render_body(
        self,
        name: str,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> str:
        del entities, connections, diagram_type, repo_root
        diagram_entities = diagram_entities or {}
        nodes = _items(diagram_entities.get("nodes"))
        edges = _items(diagram_entities.get("edges"))
        if diagram_connections:
            edges.extend(item for item in diagram_connections if isinstance(item, dict))
        return render_gsn(name, nodes, edges)

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body

    def render_svg(self, puml_body: str) -> str:
        return render_gsn_svg(puml_body)

