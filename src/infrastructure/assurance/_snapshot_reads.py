"""Read queries over the signal-snapshot aggregate.

Anchors arrive in either id form — the GUI navigates by the full slugged artifact
id, scripts and MCP callers use the short one — and SQL matches by exact equality,
so every anchor crossing this boundary goes through ``anchor_key``. Without that,
a snapshot written under one form is invisible to a reader using the other, which
surfaces as "no active snapshot" rather than as an error.
"""

from __future__ import annotations

from typing import Any

from src.domain.assurance.security_signal_snapshot import anchor_key
from src.infrastructure.assurance._snapshot_connection import SnapshotConnection


def find_snapshot_by_request(
    connection: SnapshotConnection, anchor_entity_id: str, request_id: str,
) -> dict[str, Any] | None:
    return connection.open().execute(
        "SELECT * FROM security_signal_snapshots WHERE anchor_entity_id=? AND request_id=?",
        (anchor_key(anchor_entity_id), request_id),
    ).fetchone()


def get_snapshot(connection: SnapshotConnection, snapshot_id: str) -> dict[str, Any] | None:
    return connection.open().execute(
        "SELECT * FROM security_signal_snapshots WHERE snapshot_id=?", (snapshot_id,),
    ).fetchone()


def get_active_snapshot(
    connection: SnapshotConnection, anchor_entity_id: str,
) -> dict[str, Any] | None:
    return connection.open().execute(
        "SELECT * FROM security_signal_snapshots WHERE anchor_entity_id=? AND status='active'",
        (anchor_key(anchor_entity_id),),
    ).fetchone()


def list_snapshots(
    connection: SnapshotConnection, *, anchor_entity_id: str | None = None,
) -> list[dict[str, Any]]:
    conn = connection.open()
    if anchor_entity_id:
        return conn.execute(
            "SELECT * FROM security_signal_snapshots WHERE anchor_entity_id=? "
            "ORDER BY started_at DESC",
            (anchor_key(anchor_entity_id),),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM security_signal_snapshots ORDER BY started_at DESC"
    ).fetchall()


def list_snapshot_components(
    connection: SnapshotConnection, snapshot_id: str,
) -> list[dict[str, Any]]:
    return connection.open().execute(
        "SELECT * FROM snapshot_components WHERE snapshot_id=? ORDER BY component_id",
        (snapshot_id,),
    ).fetchall()


def get_component(
    connection: SnapshotConnection, component_id: str,
) -> dict[str, Any] | None:
    """One component by its own id — the segment-safe ``SCM@…`` this system minted for it.

    Addressed by the internal id rather than by a PURL or a ``bom_ref``: those are the source's
    identifiers, they carry structure a path segment cannot, and the same package appears under
    different ones across feeds. They stay on the row as data, and as collection filters.
    """
    return connection.open().execute(
        "SELECT * FROM snapshot_components WHERE component_id=?",
        (component_id,),
    ).fetchone()


def list_snapshot_findings(
    connection: SnapshotConnection, snapshot_id: str,
) -> list[dict[str, Any]]:
    return connection.open().execute(
        "SELECT * FROM snapshot_vulnerability_findings WHERE snapshot_id=? ORDER BY finding_id",
        (snapshot_id,),
    ).fetchall()
