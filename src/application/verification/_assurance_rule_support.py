"""Shared readers for assurance verifier rules.

Store rows arrive as plain dicts with a JSON attribute blob, and every rule was re-deriving
the same three lookups. Reading them in one place keeps the rules about their subject matter
and stops a malformed blob from being handled four different ways.

The attribute reader itself is shared beyond verification — the read surfaces need the identical
lookup, and a second copy is how one of them came to read the blob's keys as columns — so it lives
in `assurance_node_attributes` and is re-exported here for the rules.
"""

from __future__ import annotations

from src.application.assurance.node_attributes import attributes_of

__all__ = ["attributes_of", "edges_from", "edges_into"]


def edges_from(
    edges: list[dict[str, object]], node_id: str, conn_type: str
) -> list[dict[str, object]]:
    """Edges of *conn_type* leaving *node_id*."""
    return [e for e in edges if str(e["source_id"]) == node_id and str(e["conn_type"]) == conn_type]


def edges_into(
    edges: list[dict[str, object]], node_id: str, conn_type: str
) -> list[dict[str, object]]:
    """Edges of *conn_type* arriving at *node_id*."""
    return [e for e in edges if str(e["target_id"]) == node_id and str(e["conn_type"]) == conn_type]
