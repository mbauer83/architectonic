"""The local changes this repository is holding, and discarding one.

Editing an artifact the engagement does not own records a change against it instead of writing. This
is where an author sees what they are holding and takes one back — the two operations that make the
recording visible rather than something that happens to them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.modeling.change_overview import RecordedChange, recorded_changes
from src.application.modeling.proposal_standing import PendingProposal, pending_proposals
from src.application.modeling.proposed_change import (
    PROPOSED_CHANGE_TYPE,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.rest.contracts.changes import (
    ChangeDiscardedResponse,
    ChangeListResponse,
    ChangeRebasedResponse,
    ChangeSubmitRequest,
    ChangeSubmittedResponse,
)
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
        "kind": change.kind,
        "changed_fields": list(change.changed_fields),
        "state": change.state,
        "condition": change.condition,
        "divergence": [
            {"field": d.field, "proposed": d.proposed, "current": d.current}
            for d in change.divergence
        ],
    }


@router.get("/api/changes", tags=[TAG_CHANGES], summary="List local changes to enterprise artifacts",
    response_model=ChangeListResponse, responses=READ_RESPONSES, operation_id="changes_list_changes")
def list_changes() -> dict[str, Any]:
    rows = [_to_dict(change) for change in recorded_changes(s.maybe_get_repo())]
    return {"changes": rows, "total": len(rows)}


@router.delete("/api/changes/{artifact_id}", tags=[TAG_CHANGES], summary="Discard a local change",
    response_model=ChangeDiscardedResponse, responses=WRITE_RESPONSES,
    operation_id="changes_discard_change")
def discard_change(artifact_id: str) -> dict[str, Any]:
    """Take a change back. The record is kept in a terminal state, not deleted."""
    from src.infrastructure.write.artifact_write.proposal_lifecycle import (
        DiscardRefused,
    )
    from src.infrastructure.write.artifact_write.proposal_lifecycle import (
        discard_change as discard,
    )

    repo = s.get_repo()
    if repo.get_entity(artifact_id) is None:
        raise HTTPException(404, f"There is no change '{artifact_id}' in this repository.")
    try:
        path, changed = s.authorized_write(
            "changes_discard_change", discard,
            repo, artifact_id=artifact_id, enterprise_root=s.maybe_enterprise_root(),
        )
    except DiscardRefused as refused:
        raise HTTPException(409, str(refused)) from refused
    if changed:
        s.clear_caches(path)
    return {"artifact_id": artifact_id, "discarded": bool(changed), "state": "abandoned"}


@router.post("/api/changes/{artifact_id}/rebase", tags=[TAG_CHANGES],
    summary="Bring a local change onto the enterprise artifact as it stands",
    response_model=ChangeRebasedResponse, responses=WRITE_RESPONSES,
    operation_id="changes_rebase_change")
def rebase_change(artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """Re-apply the change where nobody can see it, and record what it was proven against."""
    from src.infrastructure.write.artifact_write.change_rebase_op import (
        RebaseUnavailable,
        rebase_changes,
    )

    repo = s.get_repo()
    proposal = _live_change(repo, artifact_id)
    enterprise_root, registry, verifier = s.enterprise_write_deps(catalogs)
    try:
        report = s.authorized_write(
            "changes_rebase_change", rebase_changes,
            (proposal,), enterprise_root=enterprise_root, repo=repo, registry=registry,
            verifier=verifier, clear_repo_caches=s.clear_caches,
        )
    except RebaseUnavailable as refused:
        raise HTTPException(409, str(refused)) from refused
    if report.restamped:
        s.refresh_now()
    return {
        "changes": [
            {
                "artifact_id": classified.proposal_id,
                "target_id": classified.target_id,
                "outcome": classified.outcome,
                "reason": classified.reason,
                "restamped": classified.proposal_id in report.restamped,
            }
            for classified in report.rehearsed.changes
        ],
        "republished_branch": report.republished.branch if report.republished else None,
        "summary": report.summary(),
    }


@router.post("/api/changes/submit", tags=[TAG_CHANGES],
    summary="Submit local changes for review upstream",
    response_model=ChangeSubmittedResponse, responses=WRITE_RESPONSES,
    operation_id="changes_submit_changes")
def submit_changes_for_review(body: ChangeSubmitRequest,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """Replay the changes into the enterprise repository and publish the branch carrying them."""
    from src.infrastructure.write.artifact_write.change_submission import (
        SubmissionUnavailable,
        submit_changes,
    )

    enterprise_root, registry, verifier = s.enterprise_write_deps(catalogs)
    try:
        report = s.authorized_write(
            "changes_submit_changes", submit_changes,
            body.artifact_ids, repo=s.get_repo(), enterprise_root=enterprise_root,
            registry=registry, verifier=verifier, clear_repo_caches=s.clear_caches,
        )
    except (SubmissionUnavailable, ValueError) as refused:
        raise HTTPException(409, str(refused)) from refused
    s.refresh_now()
    return {
        "branch": report.branch,
        "commit": report.commit,
        "submitted": list(report.submitted),
        "pushed_now": report.pushed_now,
        "summary": (
            f"{len(report.submitted)} change"
            f"{'' if len(report.submitted) == 1 else 's'} submitted on '{report.branch}'."
        ),
    }


def _live_change(repo: Any, artifact_id: str) -> PendingProposal:
    """The change this operation is about, or the refusal that says why there is none.

    Read through `pending_proposals`, which is the one decoder of a change record — a second reading
    here would be free to disagree with the one every other surface uses.
    """
    for proposals in pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)).values():
        for proposal in proposals:
            if proposal.proposal_id == artifact_id:
                return proposal
    raise HTTPException(404, f"There is no live change '{artifact_id}' in this repository.")
