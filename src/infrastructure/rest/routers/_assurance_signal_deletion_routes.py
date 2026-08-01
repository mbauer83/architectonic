"""Deleting security-signal snapshots — the destructive half of the signal surface.

Split out when the signal router passed the size limit, and the seam is the one worth having: these
two routes destroy stored evidence, and they are the only ones here that do.

The scope of the destruction is the address. A single ``POST`` whose body chose between "this
snapshot" and "every snapshot of this anchor" made the URL say nothing about what would be removed,
and left a third case — neither selector, or both — that had to be refused at runtime. Two routes
cannot express it.

The context lookup comes from ``_assurance_signals_routes`` rather than being repeated: the
capability gate, the locked refusal and the typed denial are one decision, and a second copy of it
here is a second thing that can fall out of step with the gate it is meant to enforce.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.infrastructure.rest.contracts.assurance_signals import SecuritySnapshotDeletionResponse
from src.infrastructure.rest.routers._assurance_http import not_found as _not_found
from src.infrastructure.rest.routers._assurance_signals_routes import _mutating_context
from src.infrastructure.rest.routers._openapi import TAG_ASSURANCE

signal_deletion_router = APIRouter(tags=[TAG_ASSURANCE])


@signal_deletion_router.delete("/api/assurance/security-snapshots/{snapshot_id}",
    summary="Delete one snapshot", response_model=SecuritySnapshotDeletionResponse,
    response_model_exclude_unset=True)
def delete_security_snapshot(snapshot_id: str) -> dict[str, Any]:
    """Delete one snapshot by id.

    Two routes rather than one body-discriminated ``POST``: deleting *this snapshot* and deleting
    *every snapshot of this anchor* are different resources, and a body that selected between them
    made the URL say nothing about what would be destroyed.
    """
    from src.infrastructure.assurance.signal_deletion import delete_snapshot  # noqa: PLC0415

    ctx = _mutating_context()
    assert ctx.snapshot_store is not None  # noqa: S101 — established by the capability gate
    payload = dict(delete_snapshot(snapshot_id, snapshot_store=ctx.snapshot_store))
    if payload.get("status") != "deleted":
        raise _not_found(str(payload.get("message") or "no snapshot with that id"))
    return payload


@signal_deletion_router.delete("/api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots",
    summary="Delete every snapshot of one anchor", response_model=SecuritySnapshotDeletionResponse,
    response_model_exclude_unset=True)
def delete_anchor_security_snapshots(arch_artifact_id: str) -> dict[str, Any]:
    """The anchor-cleanup path: every snapshot for one architecture artifact."""
    from src.infrastructure.assurance.signal_deletion import delete_anchor_snapshots  # noqa: PLC0415

    ctx = _mutating_context()
    assert ctx.snapshot_store is not None  # noqa: S101 — established by the capability gate
    payload = dict(delete_anchor_snapshots(arch_artifact_id, snapshot_store=ctx.snapshot_store))
    if payload.get("status") != "deleted":
        raise _not_found(str(payload.get("message") or "this anchor has no snapshots"))
    return payload
