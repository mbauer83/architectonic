"""Failure-mode analysis REST surface.

Its own router rather than an addition to the signals routes: the two share no state, and the
signals module is already close to the length policy. Every route here is unlock-gated and
exposure-filtered like the rest of the assurance surface — a locked store answers 423 and never a
partial result.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_fmea_factors import (
    FactorInvalid,
    FactorNodeNotFound,
    FactorRecorded,
    FactorStoreLocked,
    RecordFactorRequest,
    record_factor_assessment,
)
from src.application.assurance_fmea_rows import matrix_rows
from src.domain.assurance.fmea_factors import OCCURRENCE_SCALE, FactorAssessment
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.routers._assurance_http import locked_response as _locked_response
from src.infrastructure.gui.routers._assurance_http import ok as _ok
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context

fmea_router = APIRouter()

_NO_STORE = "no-store"


def _policy() -> tuple[object, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


@fmea_router.get("/api/assurance/fmea")
def fmea_matrix(analysis_id: str | None = None) -> JSONResponse:
    """The failure-mode matrix: candidate elements crossed with the guidewords.

    Exposure-filtered before anything is assembled, so a withheld node cannot influence a count or
    a priority a caller can see. Rows are scoped to the candidate set; the causal chain behind them
    is read in full, because a failure mode's hazards belong to the analysis that produced them and
    filtering the traversal would report every matrix as incomplete.
    """
    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes())  # type: ignore[attr-defined]
    visible_ids = frozenset(str(n["node_id"]) for n in visible_nodes)
    edges = pol.filter_edges(ctx.store.list_edges(), visible_ids)  # type: ignore[attr-defined]
    scoped = [
        n for n in visible_nodes
        if analysis_id is None or str(n.get("analysis_id") or "") == analysis_id
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
    })


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
    node_id: str
    factor: str
    value: str
    justification: str
    author: str
    basis_digest: str


@fmea_router.put("/api/assurance/fmea/factor", status_code=200)
def set_fmea_factor(body: SetFactorBody) -> JSONResponse:
    """Append one factor judgement as a new revision.

    A PUT that appends rather than replaces: what is being set is *the current judgement*, and the
    revision series behind it is how a reader sees that it changed.
    """
    ctx = get_assurance_context()
    result = run_write(lambda: record_factor_assessment(
        RecordFactorRequest(
            node_id=body.node_id,
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
        return _locked_response()
    if isinstance(result, FactorNodeNotFound):
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_a_failure_mode",
                "node_id": result.node_id,
                "message": "no failure mode with this id — a factor rates a failure mode",
            },
            headers={"Cache-Control": _NO_STORE},
        )
    if isinstance(result, FactorInvalid):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_factor_assessment",
                "errors": [{"field": e.field, "message": e.message} for e in result.errors],
            },
            headers={"Cache-Control": _NO_STORE},
        )
    assert isinstance(result, FactorRecorded)
    return _ok({
        "node_id": result.node_id,
        "factor": result.factor,
        "value": result.value,
        "revision": result.revision,
        "created_at": result.created_at,
    })
