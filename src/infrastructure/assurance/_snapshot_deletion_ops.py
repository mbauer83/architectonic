"""Deleting security-signal snapshots.

Separate from the store adapter so the only destructive signal operation states
its blast radius in one place, and so the adapter is not grown further.
``SQLCipherSnapshotStore`` delegates to these functions and remains the single
object callers hold.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.assurance._archive import append_audit_row
from src.infrastructure.assurance._snapshot_connection import SnapshotConnection
from src.infrastructure.assurance._snapshot_reads import (
    get_snapshot,
    list_snapshot_components,
    list_snapshot_findings,
    list_snapshots,
)


def delete_one_snapshot(connection: SnapshotConnection, snapshot_id: str) -> dict[str, Any] | None:
    """Delete one snapshot and its OWN rows; returns what was removed, or None
    if the snapshot does not exist.

    Deleting the ACTIVE snapshot is allowed and simply leaves the anchor with
    none — a state the read model already expresses as ``no_active_snapshot``.
    The alternative (refusing) would make an anchor whose only snapshot is
    active undeletable, which is exactly the junk-anchor case deletion exists
    for. No previous snapshot is promoted back: ``superseded → active`` is not
    an allowed transition, and resurrecting stale findings as current truth
    would be worse than reporting none.

    Scope is deliberate. The FK cascade removes this snapshot's components and
    findings. It does NOT touch canonical_vulnerabilities or
    vulnerability_aliases (SHARED identity data — other snapshots resolve
    through them) or vex_assessments (keyed by anchor and vulnerability, not by
    snapshot: an assessment outlives the scan that surfaced the finding).
    """
    conn = connection.open()
    snapshot = get_snapshot(connection, snapshot_id)
    if snapshot is None:
        return None
    removed = {
        "snapshot_id": snapshot_id,
        "anchor_entity_id": str(snapshot["anchor_entity_id"]),
        "status": str(snapshot["status"]),
        "was_active": str(snapshot["status"]) == "active",
        "component_count": len(list_snapshot_components(connection, snapshot_id)),
        "finding_count": len(list_snapshot_findings(connection, snapshot_id)),
    }
    connection.begin(conn)
    try:
        # Children first: the cascade is declared, but deleting explicitly keeps
        # the unit of work correct even if PRAGMA foreign_keys is ever off.
        conn.execute(
            "DELETE FROM snapshot_vulnerability_findings WHERE snapshot_id=?", (snapshot_id,))
        conn.execute("DELETE FROM snapshot_components WHERE snapshot_id=?", (snapshot_id,))
        conn.execute(
            "DELETE FROM security_signal_snapshots WHERE snapshot_id=?", (snapshot_id,))
        append_audit_row(conn, "SIGNAL_SNAPSHOT_DELETED", payload=dict(removed))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return removed

def delete_all_for_anchor(connection: SnapshotConnection, anchor_entity_id: str) -> list[dict[str, Any]]:
    """Delete every snapshot for one anchor. Each snapshot is its own audited
    transaction, so a mid-way failure leaves a consistent store with a truthful
    audit trail rather than a partial delete recorded as whole."""
    snapshots = list_snapshots(connection, anchor_entity_id=anchor_entity_id)
    removed: list[dict[str, Any]] = []
    for snapshot in snapshots:
        outcome = delete_one_snapshot(connection, str(snapshot["snapshot_id"]))
        if outcome is not None:
            removed.append(outcome)
    return removed

