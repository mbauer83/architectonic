"""Candidate architectures and stress-analysis workspace reads."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.candidates import analysis_reads
from src.infrastructure.candidates.analysis_start import document_writer, start_analysis
from src.infrastructure.candidates.diagram_save import diagram_writer, save_as_diagram
from src.infrastructure.candidates.integrate import integrate_candidates
from src.infrastructure.rest.contracts.candidates import (
    AnalysisIncidence,
    AnalysisProgress,
    AnalysisStart,
    AnalysisStarted,
    CandidateApplication,
    CandidateApply,
    CandidateComparison,
    CandidateCreate,
    CandidateDeletion,
    CandidateDiagramSave,
    CandidateDiagramSaved,
    CandidateEdit,
    CandidateIntegrate,
    CandidateIntegration,
    CandidateList,
    CandidateOperations,
    CandidateRebase,
    CandidateResponse,
    CandidateSelection,
    CandidateStanding,
    IntegrationCheck,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._candidate_access import refusals, service
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_CANDIDATES, TAG_DOCUMENTS, WRITE_RESPONSES

router = APIRouter()


@router.get(
    "/api/candidates",
    operation_id="candidates_list_candidates",
    tags=[TAG_CANDIDATES],
    summary="List candidate architectures",
    response_model=CandidateList,
    responses=READ_RESPONSES,
)
def candidates_list_candidates() -> dict[str, Any]:
    with refusals():
        return {"candidates": service().list()}


@router.post(
    "/api/candidates",
    operation_id="candidates_create_candidate",
    tags=[TAG_CANDIDATES],
    summary="Create a candidate architecture",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def candidates_create_candidate(body: CandidateCreate) -> dict[str, Any]:
    with refusals():
        return s.authorized_write(
            "candidates_create_candidate", service().create, body.record.model_dump(exclude_unset=True),
            [edit.model_dump(exclude_unset=True) for edit in body.operations],
        )


@router.get(
    "/api/candidates/{artifact_id}",
    operation_id="candidates_read_candidate",
    tags=[TAG_CANDIDATES],
    summary="Read a candidate and its version",
    response_model=CandidateResponse,
    responses=READ_RESPONSES,
)
def candidates_read_candidate(artifact_id: str) -> dict[str, Any]:
    with refusals():
        return service().read(artifact_id)


@router.patch(
    "/api/candidates/{artifact_id}",
    operation_id="candidates_edit_candidate",
    tags=[TAG_CANDIDATES],
    summary="Edit fields of a versioned candidate",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def candidates_edit_candidate(artifact_id: str, body: CandidateEdit) -> dict[str, Any]:
    with refusals():
        return s.authorized_write(
            "candidates_edit_candidate", service().edit, artifact_id, body.based_on, body.patch.stated(),
        )


@router.post(
    "/api/candidates/{artifact_id}/operations",
    operation_id="candidates_record_operation",
    tags=[TAG_CANDIDATES],
    summary="Record edits among a draft candidate's operations",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def candidates_record_operation(artifact_id: str, body: CandidateOperations) -> dict[str, Any]:
    """Merged per claim: an edit replaces the one before it, and an edit back to its base drops it. All the
    edits are written or none; the answer is the record and its new version."""
    with refusals():
        return s.authorized_write(
            "candidates_record_operation", service().record, artifact_id, body.based_on,
            [edit.model_dump(exclude_unset=True) for edit in body.operations],
        )


@router.delete(
    "/api/candidates/{artifact_id}",
    operation_id="candidates_delete_candidate",
    tags=[TAG_CANDIDATES],
    summary="Delete a candidate nothing refers to",
    response_model=None,
    responses={
        **WRITE_RESPONSES, **READ_RESPONSES,
        200: {"model": CandidateDeletion, "description": "Dry-run plan; nothing was deleted"},
    },
    status_code=status.HTTP_204_NO_CONTENT,
)
def candidates_delete_candidate(
    artifact_id: str,
    response: Response,
    dry_run: bool = Query(True, description="Answer what the deletion would do and delete nothing (the default)."),
    based_on: str | None = Query(
        None, description="The version last read; a candidate changed since is refused with 409 instead of deleted.",
    ),
) -> dict[str, Any] | None:
    """Refused with 409, saying why and what to do first, while a candidate stacks on it, an analysis starts
    from it, an analysis's verdicts or adaptations name it, or it is integrated (kept as the record of what was
    written). A committed deletion answers 204; a dry run answers 200 with the plan."""
    with refusals():
        plan = s.authorized_write(
            "candidates_delete_candidate", service().delete, artifact_id, based_on=based_on, dry_run=dry_run,
        )
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return dict(plan)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post(
    "/api/candidates/{artifact_id}/rebase",
    operation_id="candidates_rebase_candidate",
    tags=[TAG_CANDIDATES],
    summary="Re-base a candidate's drifted operations on the current model",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def candidates_rebase_candidate(artifact_id: str, body: CandidateRebase) -> dict[str, Any]:
    """Each drifted operation keeps what it asks for and is written against the model as it stands now."""
    with refusals():
        return s.authorized_write("candidates_rebase_candidate", service().rebase, artifact_id, body.based_on)


@router.post(
    "/api/candidates/{artifact_id}/apply",
    operation_id="candidates_apply_candidate",
    tags=[TAG_CANDIDATES],
    summary="Apply a candidate's operations to the model in one write",
    response_model=CandidateApplication,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def candidates_apply_candidate(artifact_id: str, body: CandidateApply) -> dict[str, Any]:
    """Refused with 409 while an operation conflicts or has drifted; operations already there are skipped.

    All operations land or none do. On success the candidate is integrated. A dry run answers the
    refusal instead of raising it.
    """
    with refusals():
        return s.authorized_write("candidates_apply_candidate", service().apply, artifact_id, dry_run=body.dry_run)


@router.post(
    "/api/candidates/{artifact_id}/save-as-diagram",
    operation_id="candidates_save_candidate_diagram",
    tags=[TAG_CANDIDATES],
    summary="Save the generated view a candidate is drawn on as a diagram",
    response_model=CandidateDiagramSaved,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def candidates_save_candidate_diagram(
    artifact_id: str, body: CandidateDiagramSave, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """For a candidate whose stack names no stored diagram: a new diagram drawing the model's entities in its
    scope and the relations among them, as the generated view draws them, written through the diagram create;
    the candidate is then drawn on it. Nothing the candidate changes is written. Refused (409) where the
    candidate is drawn on a stored diagram already, is final, or changed since `based_on`."""
    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    with refusals():
        return s.authorized_write(
            "candidates_save_candidate_diagram", save_as_diagram, service(), artifact_id,
            diagram_writer(s.get_repo(), repo_root, verifier, s.clear_caches),
            based_on=body.based_on, name=body.name, group=body.group, dry_run=body.dry_run,
        )


@router.post(
    "/api/stress-analyses",
    operation_id="documents_start_stress_analysis",
    tags=[TAG_DOCUMENTS],
    summary="Start a stress analysis and its naive architecture",
    response_model=AnalysisStarted,
    responses=WRITE_RESPONSES,
)
def documents_start_stress_analysis(
    body: AnalysisStart, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """One write: the naive architecture and the document naming it are both written, or neither is."""
    repo_root, _registry, verifier = s.get_write_deps(catalogs)
    with refusals():
        return s.authorized_write(
            "documents_start_stress_analysis", start_analysis, service(), body.title,
            body.naive.model_dump(exclude_unset=True),
            document_writer(repo_root, verifier, s.clear_caches),
            context=body.context,
        )


@router.get(
    "/api/candidates/{artifact_id}/diff",
    operation_id="candidates_compare_candidate",
    tags=[TAG_CANDIDATES],
    summary="Compare a composed candidate against a selected base",
    response_model=CandidateComparison,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def candidates_compare_candidate(
    artifact_id: str,
    base: str = Query("model", description="Model, naive or a candidate id."),
    naive: str | None = Query(None, description="Naive candidate id when base is naive."),
    diagram: str | None = Query(
        None, description="A stored diagram to draw on, instead of the one the candidate is drawn on.",
    ),
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    with refusals():
        return service().compare(artifact_id, base, naive, diagram, catalogs.ontology)


@router.get(
    "/api/candidates/{artifact_id}/standing",
    operation_id="candidates_read_standing",
    tags=[TAG_CANDIDATES],
    summary="Read how each operation stands against the current model",
    response_model=CandidateStanding,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def candidates_read_standing(artifact_id: str) -> dict[str, Any]:
    with refusals():
        return service().standing(artifact_id)


@router.post(
    "/api/candidate-checks",
    operation_id="candidates_check_candidates",
    tags=[TAG_CANDIDATES],
    summary="Check candidate architectures for integration conflicts",
    response_model=IntegrationCheck,
    responses=READ_RESPONSES,
)
def candidates_check_candidates(body: CandidateSelection) -> dict[str, Any]:
    with refusals():
        return service().check(body.candidates)


@router.post(
    "/api/candidate-integrations",
    operation_id="candidates_integrate_candidates",
    tags=[TAG_CANDIDATES],
    summary="Integrate candidates into a new one, resolving their conflicts",
    response_model=CandidateIntegration,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def candidates_integrate_candidates(body: CandidateIntegrate) -> dict[str, Any]:
    """A new draft on the parent the candidates share, holding every operation of each, converging ones once.
    Each conflict between them is settled by a resolution, applied in order: take one party's side, drop one
    party's operation, or merge a value where each party sets one field. A dry run answers the conflicts still
    standing with the actions each permits; integrating while one stands is refused (409). Nothing is written to
    the model."""
    with refusals():
        return s.authorized_write(
            "candidates_integrate_candidates", integrate_candidates, service(), body.candidates, name=body.name,
            rationale=body.rationale, resolutions=[one.model_dump() for one in body.resolutions],
            dry_run=body.dry_run,
        )


@router.get(
    "/api/documents/{artifact_id}/progress",
    operation_id="documents_analysis_progress",
    tags=[TAG_DOCUMENTS],
    summary="Read unfinished stress analysis and coverage hints",
    response_model=AnalysisProgress,
    responses=READ_RESPONSES,
)
def documents_analysis_progress(artifact_id: str) -> dict[str, Any]:
    """Coverage reads the perspectives this repository offers (`/api/stress-perspectives`), the one vocabulary of
    kinds."""
    with refusals():
        return analysis_reads.progress(service(), artifact_id)


@router.get(
    "/api/documents/{artifact_id}/incidence",
    operation_id="documents_analysis_incidence",
    tags=[TAG_DOCUMENTS],
    summary="Read stressor hits and coupling counts",
    response_model=AnalysisIncidence,
    responses=READ_RESPONSES,
)
def documents_analysis_incidence(artifact_id: str) -> dict[str, Any]:
    with refusals():
        return analysis_reads.incidence(service(), artifact_id)
