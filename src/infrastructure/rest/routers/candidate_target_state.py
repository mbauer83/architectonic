"""Applying a candidate as a target state, and moving that into the baseline.

Its own router so the candidate router stays within the module-size limit in `STD@1777137196`; the
orchestration is `infrastructure/candidates/target_state.py`, which the MCP tools share.
"""

from typing import Any

from fastapi import APIRouter

from src.infrastructure.candidates.target_state import (
    apply_as_target_state,
    move_target_into_baseline,
    withdraw_target_state,
)
from src.infrastructure.rest.contracts.candidates import (
    CandidateApply,
    CandidateMove,
    CandidateTargetStateApplication,
    CandidateWithdrawal,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._candidate_access import refusals, service
from src.infrastructure.rest.routers._openapi import TAG_CHANGES, WRITE_RESPONSES

router = APIRouter()


@router.post(
    "/api/change-sets/{artifact_id}/apply-as-target-state",
    operation_id="changes_apply_candidate_as_target_state",
    tags=[TAG_CHANGES],
    summary="Write a candidate into the model as a target state beside the baseline",
    response_model=CandidateTargetStateApplication,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def changes_apply_candidate_as_target_state(artifact_id: str, body: CandidateApply) -> dict[str, Any]:
    """An added element as a draft, a changed one as "‹name› (target)" with its relations and a trace to the
    original, a Baseline and a Target plateau with a «gap» between them, in one write; the candidate's
    operations are kept unapplied to the originals. Refused with 409 as a direct apply is, and while its
    target state is already in the model. A dry run answers what would be written.
    """
    with refusals():
        return s.authorized_write(
            "changes_apply_candidate_as_target_state", apply_as_target_state, service(), artifact_id,
            dry_run=body.dry_run,
        )


@router.post(
    "/api/change-sets/{artifact_id}/move-into-baseline",
    operation_id="changes_move_candidate_into_baseline",
    tags=[TAG_CHANGES],
    summary="Move a candidate's target state into the baseline",
    response_model=CandidateMove,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def changes_move_candidate_into_baseline(artifact_id: str, body: CandidateApply) -> dict[str, Any]:
    """The kept operations applied to the originals, the copies' relations moved back, the copies, plateaus
    and gap removed, and the added elements made active — one generated list, refused with 409 while an
    operation conflicts or has drifted. On success the candidate is integrated.
    """
    with refusals():
        return s.authorized_write(
            "changes_move_candidate_into_baseline", move_target_into_baseline, service(), artifact_id,
            dry_run=body.dry_run,
        )


@router.post(
    "/api/change-sets/{artifact_id}/withdraw-target-state",
    operation_id="changes_withdraw_candidate_target_state",
    tags=[TAG_CHANGES],
    summary="Withdraw a candidate's target state from the model, leaving the baseline as it was",
    response_model=CandidateWithdrawal,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def changes_withdraw_candidate_target_state(artifact_id: str, body: CandidateApply) -> dict[str, Any]:
    """The copies with their relations and traces, the added elements, the plateaus and the gap removed as one
    generated list; the candidate is then a draft again, to be applied, re-applied, rejected or deleted. Refused
    with 409 while something written since refers to one of them: a relation the target state did not write, or a
    diagram drawing one, each named. A dry run answers the removals and the refusal.
    """
    with refusals():
        return s.authorized_write(
            "changes_withdraw_candidate_target_state", withdraw_target_state, service(), artifact_id,
            dry_run=body.dry_run,
        )
