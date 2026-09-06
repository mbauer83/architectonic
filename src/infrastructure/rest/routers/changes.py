"""The local changes this repository is holding, and discarding one.

Editing an artifact the engagement does not own records a change against it instead of writing. This
is where an author sees what they are holding and takes one back — the two operations that make the
recording visible rather than something that happens to them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.application.modeling.change_overview import RecordedChange, recorded_changes
from src.application.modeling.proposed_change import PENDING_STATES, PROPOSAL_STATE
from src.infrastructure.rest.contracts.changes import ChangeDiscardedResponse, ChangeListResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_CHANGES,
    WRITE_RESPONSES,
)

router = APIRouter()


def _to_dict(change: RecordedChange) -> dict[str, Any]:
    return {
        "artifact_id": change.change_id,
        "target_id": change.target_id,
        "target_name": change.target_name,
        "reference_id": change.reference_id,
        "kind": change.kind,
        "changed_fields": list(change.changed_fields),
        "state": change.state,
        "condition": change.condition,
        "divergence": [
            {"field": d.field, "proposed": d.proposed, "current": d.current}
            for d in change.divergence
        ],
    }


@router.get("/api/changes", tags=[TAG_CHANGES], summary="List local changes awaiting review",
    response_model=ChangeListResponse, responses=READ_RESPONSES, operation_id="changes_list_changes")
def list_changes() -> dict[str, Any]:
    rows = [_to_dict(change) for change in recorded_changes(s.maybe_get_repo())]
    return {"changes": rows, "total": len(rows)}


@router.delete("/api/changes/{artifact_id}", tags=[TAG_CHANGES], summary="Discard a local change",
    response_model=ChangeDiscardedResponse, responses=WRITE_RESPONSES,
    operation_id="changes_discard_change")
def discard_change(artifact_id: str) -> dict[str, Any]:
    """Take a change back. The record is kept in a terminal state, not deleted."""
    from src.infrastructure.write.artifact_write.proposal_lifecycle import mark_proposal_state

    repo = s.get_repo()
    record = repo.get_entity(artifact_id)
    if record is None:
        raise HTTPException(404, f"There is no change '{artifact_id}' in this repository.")
    if str(record.extra.get(PROPOSAL_STATE, "")) not in PENDING_STATES:
        raise HTTPException(
            409,
            f"'{artifact_id}' has already ended; a change that is integrated or abandoned is a "
            "record of what happened and is not changed again.",
        )
    changed = s.authorized_write(
        "changes_discard_change", mark_proposal_state,
        record.path, artifact_id=artifact_id, state="abandoned",
    )
    if changed:
        s.clear_caches(record.path)
    return {"artifact_id": artifact_id, "discarded": bool(changed), "state": "abandoned"}
