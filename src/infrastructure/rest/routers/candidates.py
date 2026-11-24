"""Candidate architectures and stress-analysis workspace reads."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.candidates.repository import CandidateConflict
from src.infrastructure.candidates.service import CandidateService, document_writer
from src.infrastructure.rest.contracts.candidates import (
    AnalysisIncidence,
    AnalysisProgress,
    AnalysisStart,
    AnalysisStarted,
    CandidateComparison,
    CandidateCreate,
    CandidateEdit,
    CandidateList,
    CandidateOperation,
    CandidateRebase,
    CandidateResponse,
    CandidateSelection,
    CandidateStanding,
    IntegrationCheck,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_CHANGES, TAG_DOCUMENTS, WRITE_RESPONSES

router = APIRouter()


def _service() -> CandidateService:
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(503, "Engagement repository is not initialised")
    return CandidateService(root)


@contextmanager
def _refusals() -> Iterator[None]:
    try:
        yield
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except CandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/api/change-sets",
    operation_id="changes_list_candidates",
    tags=[TAG_CHANGES],
    summary="List candidate architectures",
    response_model=CandidateList,
    responses=READ_RESPONSES,
)
def changes_list_candidates() -> dict[str, Any]:
    with _refusals():
        return {"candidates": _service().list()}


@router.post(
    "/api/change-sets",
    operation_id="changes_create_candidate",
    tags=[TAG_CHANGES],
    summary="Create a candidate architecture",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def changes_create_candidate(body: CandidateCreate) -> dict[str, Any]:
    with _refusals():
        return s.authorized_write("changes_create_candidate", _service().create, body.record, body.diagram)


@router.get(
    "/api/change-sets/{artifact_id}",
    operation_id="changes_read_candidate",
    tags=[TAG_CHANGES],
    summary="Read a candidate and its version",
    response_model=CandidateResponse,
    responses=READ_RESPONSES,
)
def changes_read_candidate(artifact_id: str) -> dict[str, Any]:
    with _refusals():
        return _service().read(artifact_id)


@router.patch(
    "/api/change-sets/{artifact_id}",
    operation_id="changes_edit_candidate",
    tags=[TAG_CHANGES],
    summary="Edit fields of a versioned candidate",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def changes_edit_candidate(artifact_id: str, body: CandidateEdit) -> dict[str, Any]:
    with _refusals():
        return s.authorized_write("changes_edit_candidate", _service().edit, artifact_id, body.based_on, body.patch)


@router.post(
    "/api/change-sets/{artifact_id}/operations",
    operation_id="changes_record_operation",
    tags=[TAG_CHANGES],
    summary="Record an edit among a candidate's operations",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def changes_record_operation(artifact_id: str, body: CandidateOperation) -> dict[str, Any]:
    """Merged per claim: an edit replaces the one before it, and an edit back to its base drops it."""
    with _refusals():
        return s.authorized_write(
            "changes_record_operation", _service().record, artifact_id, body.based_on, body.operation,
        )


@router.delete(
    "/api/change-sets/{artifact_id}",
    operation_id="changes_delete_candidate",
    tags=[TAG_CHANGES],
    summary="Delete a candidate nothing stacks on and no analysis starts from",
    response_model=None,
    responses={**WRITE_RESPONSES, **READ_RESPONSES},
    status_code=status.HTTP_204_NO_CONTENT,
)
def changes_delete_candidate(artifact_id: str) -> Response:
    """Refused with 409, saying why, while a candidate stacks on it or an analysis names it as its naive."""
    with _refusals():
        s.authorized_write("changes_delete_candidate", _service().delete, artifact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/change-sets/{artifact_id}/rebase",
    operation_id="changes_rebase_candidate",
    tags=[TAG_CHANGES],
    summary="Re-base a candidate's drifted operations on the current model",
    response_model=CandidateResponse,
    responses=WRITE_RESPONSES,
)
def changes_rebase_candidate(artifact_id: str, body: CandidateRebase) -> dict[str, Any]:
    """Each drifted operation keeps what it asks for and is written against the model as it stands now."""
    with _refusals():
        return s.authorized_write("changes_rebase_candidate", _service().rebase, artifact_id, body.based_on)


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
    with _refusals():
        return s.authorized_write(
            "documents_start_stress_analysis", _service().start, body.title, body.naive,
            document_writer(repo_root, verifier, s.clear_caches),
            question=body.question, scope_diagram=body.scope_diagram,
        )


@router.get(
    "/api/change-sets/{artifact_id}/diff",
    operation_id="changes_compare_candidate",
    tags=[TAG_CHANGES],
    summary="Compare a composed candidate against a selected base",
    response_model=CandidateComparison,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def changes_compare_candidate(
    artifact_id: str,
    base: str = Query("model", description="Model, naive or a candidate id."),
    naive: str | None = Query(None, description="Naive candidate id when base is naive."),
    diagram: str | None = Query(None, description="Stored diagram for canvas geometry."),
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    with _refusals():
        return _service().compare(artifact_id, base, naive, diagram, catalogs.ontology)


@router.get(
    "/api/change-sets/{artifact_id}/standing",
    operation_id="changes_read_standing",
    tags=[TAG_CHANGES],
    summary="Read how each operation stands against the current model",
    response_model=CandidateStanding,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def changes_read_standing(artifact_id: str) -> dict[str, Any]:
    with _refusals():
        return _service().standing(artifact_id)


@router.post(
    "/api/change-set-checks",
    operation_id="changes_check_candidates",
    tags=[TAG_CHANGES],
    summary="Check candidate architectures for integration conflicts",
    response_model=IntegrationCheck,
    responses=READ_RESPONSES,
)
def changes_check_candidates(body: CandidateSelection) -> dict[str, Any]:
    with _refusals():
        return _service().check(body.candidates)


@router.get(
    "/api/documents/{artifact_id}/progress",
    operation_id="documents_analysis_progress",
    tags=[TAG_DOCUMENTS],
    summary="Read unfinished stress analysis and coverage hints",
    response_model=AnalysisProgress,
    responses=READ_RESPONSES,
)
def documents_analysis_progress(
    artifact_id: str, kinds: list[str] = Query(default=[], description="Stress categories to check for coverage.")
) -> dict[str, Any]:
    with _refusals():
        return _service().progress(artifact_id, kinds)


@router.get(
    "/api/documents/{artifact_id}/incidence",
    operation_id="documents_analysis_incidence",
    tags=[TAG_DOCUMENTS],
    summary="Read stressor hits and coupling counts",
    response_model=AnalysisIncidence,
    responses=READ_RESPONSES,
)
def documents_analysis_incidence(artifact_id: str) -> dict[str, Any]:
    with _refusals():
        return _service().incidence(artifact_id)
