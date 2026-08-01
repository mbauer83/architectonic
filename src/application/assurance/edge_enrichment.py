"""Endpoint enrichment for policy-filtered assurance edges.

Decorates edges with endpoint names and node types so navigation surfaces can
render links without client-side lookup loops. Confidentiality is upstream:
callers MUST pass edges already filtered by `AssuranceExposurePolicy.filter_edges`
over the same visible-node set — enrichment only ever reads visible nodes. A
lookup miss therefore means the caller broke that contract (or an endpoint was
deleted between reads); the edge is omitted, never rendered with a placeholder,
and dangling edges surface exclusively through the privileged verifier.
"""

from __future__ import annotations

from typing import Any


def visible_nodes_by_id(visible_nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(n["node_id"]): n for n in visible_nodes}


def enrich_edges(
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return policy-filtered edges decorated with endpoint name/node_type."""
    enriched: list[dict[str, Any]] = []
    for edge in edges:
        source = nodes_by_id.get(str(edge.get("source_id", "")))
        target = nodes_by_id.get(str(edge.get("target_id", "")))
        if source is None or target is None:
            continue
        enriched.append({
            **edge,
            "source_name": str(source.get("name", "")),
            "source_type": str(source.get("node_type", "")),
            "target_name": str(target.get("name", "")),
            "target_type": str(target.get("node_type", "")),
        })
    return enriched
