"""SignalReadToken (§6.0(f)) — pin one consistent signal snapshot across a
batch of reads.

The token covers: the availability revision (bumped by lock/unlock/
reconfigure — exposed through an inward-facing port, never the connection
manager itself), the active snapshot identity for the anchor, the exposure ceiling,
and the VEX revision state for the anchor. Batch reads happen under one token
and the caller revalidates before returning; ANY revision change makes the
result ``unavailable/retry`` — never partial values mixing two snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class AvailabilityState(Protocol):
    """Inward-facing availability port: a monotonic revision that changes on
    lock, unlock, and reconfiguration."""

    def availability_revision(self) -> int: ...


class SnapshotReads(Protocol):
    def get_active_snapshot(self, anchor_entity_id: str) -> Mapping[str, Any] | None: ...


class SnapshotVexReads(Protocol):
    def list_anchor_assessments(self, anchor_entity_id: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class SignalReadToken:
    anchor_entity_id: str
    availability_revision: int
    active_snapshot_id: str | None
    active_snapshot_activated_at: str | None
    exposure_ceiling: str
    vex_revision_count: int


def take_snapshot(
    anchor_entity_id: str,
    *,
    availability: AvailabilityState,
    snapshot_store: SnapshotReads,
    vex_store: SnapshotVexReads,
    exposure_ceiling: str,
) -> SignalReadToken:
    snapshot = snapshot_store.get_active_snapshot(anchor_entity_id)
    return SignalReadToken(
        anchor_entity_id=anchor_entity_id,
        availability_revision=availability.availability_revision(),
        active_snapshot_id=None if snapshot is None else str(snapshot["snapshot_id"]),
        active_snapshot_activated_at=None if snapshot is None else str(snapshot.get("activated_at") or ""),
        exposure_ceiling=exposure_ceiling,
        vex_revision_count=len(vex_store.list_anchor_assessments(anchor_entity_id)),
    )


def snapshot_still_valid(
    token: SignalReadToken,
    *,
    availability: AvailabilityState,
    snapshot_store: SnapshotReads,
    vex_store: SnapshotVexReads,
    exposure_ceiling: str,
) -> bool:
    """Revalidation: recompute the token and require exact equality — a changed
    snapshot, ceiling, VEX state, or availability generation invalidates the batch."""
    return token == take_snapshot(
        token.anchor_entity_id,
        availability=availability,
        snapshot_store=snapshot_store,
        vex_store=vex_store,
        exposure_ceiling=exposure_ceiling,
    )

def evaluate_pinned(
    anchor_entity_id: str,
    *,
    availability: AvailabilityState,
    snapshot_store: Any,
    vex_store: Any,
    exposure_ceiling: str,
    evaluate: Any,
) -> tuple[Any | None, SignalReadToken]:
    """Run ``evaluate()`` under one snapshot token and revalidate before
    returning. Returns (result, token) — result is None when any covered
    revision changed mid-evaluation; the caller reports unavailable/retry,
    never partial values."""
    token = take_snapshot(
        anchor_entity_id, availability=availability, snapshot_store=snapshot_store,
        vex_store=vex_store, exposure_ceiling=exposure_ceiling,
    )
    result = evaluate()
    if not snapshot_still_valid(
        token, availability=availability, snapshot_store=snapshot_store,
        vex_store=vex_store, exposure_ceiling=exposure_ceiling,
    ):
        return None, token
    return result, token
