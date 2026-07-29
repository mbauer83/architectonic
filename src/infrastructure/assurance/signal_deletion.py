"""The one boundary for deleting security-signal snapshots.

Mirrors ``signal_ingest``: both transports (REST, MCP) gate on the same
signal-mutation capability, perform the delete through the same serialised write,
and render the same body — they differ only in how a denial is expressed. Deletion
is a destructive signal mutation, so it runs under the same capability predicate
and lands the same kind of audit row as an ingest.

Deleting the ACTIVE snapshot is permitted and leaves the anchor reporting
``no_active_snapshot``. Refusing would make an anchor whose only snapshot is
active impossible to remove, which is the case deletion mostly exists for; and no
earlier snapshot is promoted back, because ``superseded → active`` is not an
allowed transition and presenting stale findings as current truth is worse than
presenting none.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

# HTTP status per deletion outcome; the MCP surface reports the same `status`
# string and ignores the code, so both transports stay in lockstep.
DELETE_STATUS_CODES: Mapping[str, int] = {
    "deleted": 200,
    "not_found": 404,
    "nothing_to_delete": 404,
}


class SnapshotDeletionStore(Protocol):
    """The deletion slice of the snapshot store."""

    def delete_snapshot(self, snapshot_id: str) -> Mapping[str, Any] | None: ...

    # Sequence, not list: list is invariant, so a list[dict] implementation would
    # not satisfy a list[Mapping] protocol.
    def delete_anchor_snapshots(self, anchor_entity_id: str) -> Sequence[Mapping[str, Any]]: ...


def delete_snapshot(
    snapshot_id: str, *, snapshot_store: SnapshotDeletionStore,
) -> dict[str, object]:
    """Delete one snapshot by id, on the serialised assurance writer."""
    from src.infrastructure.assurance.write_serialization import run_write  # noqa: PLC0415

    removed = run_write(lambda: snapshot_store.delete_snapshot(snapshot_id))
    if removed is None:
        return {
            "status": "not_found",
            "snapshot_id": snapshot_id,
            "message": "No snapshot with that id; nothing was deleted.",
        }
    return {"status": "deleted", "deleted": [dict(removed)], "deleted_count": 1}


def delete_anchor_snapshots(
    anchor_entity_id: str, *, snapshot_store: SnapshotDeletionStore,
) -> dict[str, object]:
    """Delete every snapshot for one anchor — the anchor-cleanup path."""
    from src.infrastructure.assurance.write_serialization import run_write  # noqa: PLC0415

    removed = run_write(lambda: snapshot_store.delete_anchor_snapshots(anchor_entity_id))
    if not removed:
        return {
            "status": "nothing_to_delete",
            "anchor_entity_id": anchor_entity_id,
            "message": "That anchor has no snapshots; nothing was deleted.",
        }
    return {
        "status": "deleted",
        "anchor_entity_id": anchor_entity_id,
        "deleted": [dict(entry) for entry in removed],
        "deleted_count": len(removed),
    }
