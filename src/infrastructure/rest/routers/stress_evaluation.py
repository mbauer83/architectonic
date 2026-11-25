"""A stress analysis's test set: its read, the hold-out, a candidate's residuality, and the perspectives."""

from typing import Any

from fastapi import APIRouter, Depends

from src.application.artifacts.document_part_edits import TableRowEdits
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.candidates import evaluation
from src.infrastructure.candidates.evaluation import TableWriter
from src.infrastructure.rest.contracts.stress_evaluation import (
    AnalysisEvaluation,
    CandidateResiduality,
    HeldOut,
    HoldOut,
    StressPerspectives,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._candidate_access import refusals, service
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_CHANGES, TAG_DOCUMENTS, WRITE_RESPONSES
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.document import edit_document
from src.infrastructure.write.artifact_write.types import WriteResult

router = APIRouter()


def _table_writer(catalogs: RuntimeCatalogs) -> TableWriter:
    """Rows written as the document's row-batch route writes them: one verified document edit."""
    repo_root, registry, verifier = s.get_write_deps(catalogs)

    def write(artifact_id: str, edits: TableRowEdits, dry_run: bool) -> WriteResult:
        return edit_document(
            assert_write_root=assert_engagement_write_root, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=s.clear_caches, artifact_id=artifact_id, registry=registry, repo=s.maybe_get_repo(),
            part=edits, title=None, body=None, keywords=None, extra_frontmatter=None, status=None, version=None,
            last_updated=None, dry_run=dry_run,
        )

    return write


@router.get(
    "/api/documents/{artifact_id}/test-set",
    operation_id="documents_analysis_test_set",
    tags=[TAG_DOCUMENTS],
    summary="Read a stress analysis's test set, its verdicts and the residuality they give",
    response_model=AnalysisEvaluation,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def documents_analysis_test_set(artifact_id: str) -> dict[str, Any]:
    """Residuality (Y − X) / n is given once an architecture and the naive are judged on every usable stressor."""
    with refusals():
        return evaluation.evaluation(service(), artifact_id)


@router.post(
    "/api/documents/{artifact_id}/test-set/hold-out",
    operation_id="documents_hold_out_test_set",
    tags=[TAG_DOCUMENTS],
    summary="Hold a random third of the design stressors out into the test set",
    response_model=HeldOut,
    responses=WRITE_RESPONSES,
)
def documents_hold_out_test_set(
    artifact_id: str, body: HoldOut, catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """The seed drawn with is answered, so the same draw can be made again. Fewer than three design stressors: 422."""
    writer = _table_writer(catalogs)
    with refusals():
        return s.authorized_write(
            "documents_hold_out_test_set", evaluation.hold_out, service(), artifact_id, writer,
            seed=body.seed, dry_run=body.dry_run,
        )


@router.get(
    "/api/change-sets/{artifact_id}/residuality",
    operation_id="changes_read_residuality",
    tags=[TAG_CHANGES],
    summary="Read a candidate's residuality in each analysis that judged it",
    response_model=CandidateResiduality,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def changes_read_residuality(artifact_id: str) -> dict[str, Any]:
    with refusals():
        return evaluation.residuality_by_analysis(service(), artifact_id)


@router.get(
    "/api/stress-perspectives",
    operation_id="documents_list_stress_perspectives",
    tags=[TAG_DOCUMENTS],
    summary="List the perspectives offered to whoever writes stressors",
    response_model=StressPerspectives,
    responses=READ_RESPONSES,
)
def documents_list_stress_perspectives() -> dict[str, Any]:
    """Each framework's perspectives with a guiding question; none names an element of any architecture. The
    shipped frameworks, with the repository's own from `.arch-repo/stress-perspectives.json` laid over them; 422
    where that file cannot be read."""
    with refusals():
        return evaluation.perspectives(service())
