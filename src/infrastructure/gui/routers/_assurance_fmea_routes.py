"""Failure-mode analysis REST surface.

Its own router rather than an addition to the signals routes: the two share no state, and the
signals module is already close to the length policy. Every route here is unlock-gated and
exposure-filtered like the rest of the assurance surface — a locked store answers 423 and never a
partial result.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.application.assurance_exposure import AssuranceExposurePolicy, Visible
from src.application.assurance_fmea_factors import (
    FactorInvalid,
    FactorLegacyInvalid,
    FactorNodeNotFound,
    FactorRecorded,
    FactorStoreLocked,
    RecordFactorRequest,
    record_factor_assessment,
)
from src.application.assurance_fmea_rows import matrix_rows
from src.application.assurance_legacy_invalid import LegacyInvalidNode
from src.domain.assurance.fmea_factors import OCCURRENCE_SCALE, FactorAssessment
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.contracts.assurance_fmea import (
    FmeaFactorRecordedResponse,
    FmeaMatrixResponse,
)
from src.infrastructure.gui.contracts.errors import (
    ApiError,
    FieldError,
    LegacyInvalidDetails,
    MethodMismatchDetails,
    NotAFailureModeDetails,
    ValidationErrorDetails,
)
from src.infrastructure.gui.routers._assurance_http import locked_response as _locked_response
from src.infrastructure.gui.routers._assurance_http import not_found_response as _not_found_response
from src.infrastructure.gui.routers._assurance_http import ok as _ok
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context

fmea_router = APIRouter()

_NO_STORE = "no-store"


def _policy() -> tuple[object, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


@fmea_router.get("/api/assurance/analyses/{analysis_id}/matrix",
    response_model=FmeaMatrixResponse)
def fmea_matrix(analysis_id: str) -> JSONResponse:
    """The failure-mode matrix of one analysis: candidate elements crossed with the guidewords.

    The analysis is required, and it is the path. Unscoped, this returned every failure mode in the
    store under a heading that said "all" — a matrix is a projection *of an analysis*, and there is
    no analysis-free reading of a priority ranking. An analysis of another method has no matrix, so
    that is a typed 409 rather than an empty grid that reads like a clean sheet.

    Exposure-filtered before anything is assembled, so a withheld node cannot influence a count or
    a priority a caller can see. Rows are scoped to the candidate set; the causal chain behind them
    is read in full, because a failure mode's hazards belong to the analysis that produced them and
    filtering the traversal would report every matrix as incomplete.
    """
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))  # type: ignore[attr-defined]
    if not isinstance(outcome, Visible):
        raise _not_found_response()
    method = str(outcome.value.get("method") or "")
    if method != "FMEA":
        raise ApiError(
            409,
            "analysis_method_mismatch",
            "a failure-mode matrix is a projection of an FMEA analysis",
            MethodMismatchDetails(
                analysis_id=analysis_id, expected_method="FMEA", actual_method=method,
            ),
        )
    visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes())  # type: ignore[attr-defined]
    visible_ids = frozenset(str(n["node_id"]) for n in visible_nodes)
    edges = pol.filter_edges(ctx.store.list_edges(), visible_ids)  # type: ignore[attr-defined]
    scoped = [
        n for n in visible_nodes
        if str(n.get("analysis_id") or "") == analysis_id
        or str(n.get("node_type", "")) != "failure-mode"
    ]
    failure_mode_ids = [
        str(n["node_id"]) for n in scoped if str(n.get("node_type", "")) == "failure-mode"
    ]
    stored = ctx.store.read_fmea_assessments(failure_mode_ids)  # type: ignore[attr-defined]
    rows = matrix_rows(
        nodes=scoped,
        edges=edges,
        arch_refs=ctx.store.list_arch_refs(),  # type: ignore[attr-defined]
        assessments={
            node_id: [_as_assessment(row) for row in revisions]
            for node_id, revisions in stored.items()
        },
        basis=current_architecture_basis(),
    )
    # The occurrence vocabulary travels with the matrix. A recording surface has to offer the
    # members of the scale and nothing else, and restating them in the client would be a second
    # source of truth for an ordinal set whose order is load-bearing.
    return _ok({
        "analysis_id": analysis_id,
        "rows": rows,
        "count": len(rows),
        "occurrence_scale": list(OCCURRENCE_SCALE),
    }, FmeaMatrixResponse)


def _as_assessment(row: dict[str, object]) -> FactorAssessment:
    return FactorAssessment(
        node_id=str(row.get("node_id") or ""),
        factor=str(row.get("factor") or ""),
        basis_digest=str(row.get("basis_digest") or ""),
        revision=int(str(row.get("revision") or 0)),
        value=str(row.get("value") or ""),
        justification=str(row.get("justification") or ""),
        author=str(row.get("author") or ""),
        created_at=str(row.get("created_at") or ""),
    )


class SetFactorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor: str
    value: str
    justification: str
    author: str
    basis_digest: str


@fmea_router.post("/api/assurance/nodes/{node_id}/factor-assessments", status_code=200,
    response_model=FmeaFactorRecordedResponse)
def set_fmea_factor(node_id: str, body: SetFactorBody) -> JSONResponse:
    """Append one factor judgement to a failure mode's assessment series.

    POST, not PUT: this *appends a revision* rather than replacing a value, so PUT would have
    promised an idempotence the surface does not have — sending the same judgement twice produces
    two revisions, and that is the point of keeping the series. The node is the path; its own
    provenance decides which analysis owns the judgement, so no body names one.
    """
    ctx = get_assurance_context()
    result = run_write(lambda: record_factor_assessment(
        RecordFactorRequest(
            node_id=node_id,
            factor=body.factor,
            value=body.value,
            justification=body.justification,
            author=body.author,
            basis_digest=body.basis_digest,
        ),
        store=ctx.store,
        archive=ctx.archive,
    ))
    if isinstance(result, FactorStoreLocked):
        raise _locked_response()
    if isinstance(result, FactorLegacyInvalid):
        raise ApiError(
            409,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    if isinstance(result, FactorNodeNotFound):
        raise ApiError(
            404,
            "not_a_failure_mode",
            "No failure mode with this id — a factor rates a failure mode.",
            NotAFailureModeDetails(node_id=result.node_id),
        )
    if isinstance(result, FactorInvalid):
        # `validation_error`: these are field rejections, and `FieldError` is where every surface on
        # this API carries them. A code of its own would have made a client branch on the *route* to
        # find out how to read a field error.
        raise ApiError(
            422,
            "validation_error",
            "The factor assessment was rejected.",
            ValidationErrorDetails(
                field_errors=[FieldError(field=e.field, message=e.message) for e in result.errors]
            ),
        )
    assert isinstance(result, FactorRecorded)
    return _ok({
        "node_id": result.node_id,
        "factor": result.factor,
        "value": result.value,
        "revision": result.revision,
        "created_at": result.created_at,
    }, FmeaFactorRecordedResponse)
