"""What a canvas save's diagram rows carry beside the rows themselves.

The transports send a diagram's connections inside its entity rows under `_connections`, and a drawn
connection names the model connection it represents as `backing_conn_id`. Neither is stored as sent:
the connections are written as the diagram's own, and each backing becomes an explicit binding.
"""

from __future__ import annotations

from typing import Any


def split_diagram_entities(
    diagram_entities: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Separate the transport-only `_connections` key from entity data."""
    if diagram_entities is None:
        return None, None
    conns = diagram_entities.get("_connections")
    if conns is None:
        return diagram_entities, None
    clean = {k: v for k, v in diagram_entities.items() if k != "_connections"}
    return clean or None, conns if isinstance(conns, list) else None


def extract_conn_bindings(
    connections: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Strip `backing_conn_id` from connections; return (clean, binding_dicts)."""
    if not connections:
        return connections, []
    bindings: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            clean.append(conn)
            continue
        backing_id = conn.get("backing_conn_id")
        conn_id = conn.get("id")
        if backing_id and conn_id:
            bindings.append({
                "id": f"bind-conn-{conn_id}",
                "subject": {"kind": "connection", "id": conn_id},
                "correspondence_kind": "represents",
                "target": {"connection_id": backing_id},
            })
        clean.append({k: v for k, v in conn.items() if k != "backing_conn_id"})
    return clean or None, bindings
