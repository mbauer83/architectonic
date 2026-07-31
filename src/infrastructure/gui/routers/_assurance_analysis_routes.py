"""Unlock-gated HTTP endpoints for the assurance analysis aggregate + STPA method.

An analysis is the aggregate root for a unit of STPA/CAST/GRC work. Reads are
exposure-filtered (above-ceiling analyses are omitted from lists and 404 on direct
read); writes go through the application use cases (audited). Also hosts the
method-support endpoints the wizards call: per-step guidance (always callable) and
analysis-scoped STPA completeness.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.application import assurance_analysis as uc
from src.application.assurance_exposure import NotFound, Visible
from src.application.assurance_gsn import build_gsn_draft, record_publication
from src.application.assurance_guidance import lookup as guidance_lookup
from src.application.assurance_legacy_invalid import LegacyInvalidNode
from src.application.verification.case_draft import case_completeness_from_records
from src.application.verification.cast_complete import run_cast_complete
from src.application.verification.grc_complete import run_grc_complete
from src.application.verification.stpa_complete import run_stpa_complete
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.contracts.errors import (
    ApiError,
    LegacyInvalidDetails,
    MethodMismatchDetails,
)
from src.infrastructure.gui.routers._assurance_http import (
    NO_STORE,
    build_policy,
    locked_response,
    not_found_response,
    ok,
)
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

analysis_router = APIRouter()


class CreateAnalysisBody(BaseModel):
    name: str
    method: str
    architecture_anchor_id: str = ""
    tlp: str = "TLP:WHITE"
    status: str = "draft"


class UpdateAnalysisBody(BaseModel):
    name: str | None = None
    status: str | None = None
    tlp: str | None = None


class GsnPublicationBinding(BaseModel):
    assurance_node_id: str
    gsn_node_id: str


class RecordGsnPublicationBody(BaseModel):
    """The analysis is the path; the body names only what is being published."""

    model_config = ConfigDict(extra="forbid")

    diagram_id: str
    source_bindings: list[GsnPublicationBinding] = Field(default_factory=list)


def _invalid(result: uc.AnalysisInvalid) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": result.error, "message": result.message},
        headers={"Cache-Control": NO_STORE},
    )


def _visible_gsn_graph(
    analysis_id: str,
) -> tuple[
    AssuranceContext,
    Visible | NotFound,
    list[dict[str, object]],
    list[dict[str, object]],
    bool,
]:
    ctx, pol = build_policy()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    nodes, withheld = pol.filter_nodes(ctx.store.list_nodes(analysis_id=analysis_id))
    node_ids = frozenset(str(node["node_id"]) for node in nodes)
    edges = pol.filter_edges(ctx.store.list_edges(), node_ids)
    return ctx, outcome, nodes, edges, withheld > 0


# ── Reads ───────────────────────────────────────────────────────────────────────


@analysis_router.get("/api/assurance/analyses")
def list_analyses(method: str | None = None, status: str | None = None) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    analyses = ctx.store.list_analyses(method=method, status=status)
    visible, _withheld = pol.filter_analyses(analyses)
    scope = pol.scope()
    return ok({
        "analyses": visible,
        "count": len(visible),
        "visibility_limited": scope.visibility_limited,
    })


@analysis_router.get("/api/assurance/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    if isinstance(outcome, Visible):
        # Visible node count scoped to this analysis (exposure-filtered).
        visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes(analysis_id=analysis_id))
        return ok({"analysis": outcome.value, "node_count": len(visible_nodes)})
    return not_found_response()


# ── Writes ──────────────────────────────────────────────────────────────────────


@analysis_router.post("/api/assurance/analyses", status_code=200)
def create_analysis(body: CreateAnalysisBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        return locked_response()
    result = run_write(lambda: uc.create_analysis(
        ctx.store, ctx.archive,
        name=body.name, method=body.method,
        architecture_anchor_id=body.architecture_anchor_id,
        tlp=body.tlp, status=body.status,
    ))
    return _translate_write(result)


@analysis_router.patch("/api/assurance/analyses/{analysis_id}", status_code=200)
def update_analysis(analysis_id: str, body: UpdateAnalysisBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        return locked_response()
    result = run_write(lambda: uc.update_analysis(
        ctx.store, ctx.archive,
        analysis_id=analysis_id,
        name=body.name, status=body.status, tlp=body.tlp,
    ))
    return _translate_write(result)


@analysis_router.delete("/api/assurance/analyses/{analysis_id}", status_code=200)
def delete_analysis(analysis_id: str) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        return locked_response()
    result = run_write(lambda: uc.delete_analysis(
        ctx.store, ctx.archive, analysis_id=analysis_id,
    ))
    return _translate_write(result)


def _translate_write(result: uc.AnalysisResult) -> JSONResponse:
    if isinstance(result, uc.AnalysisLocked):
        return locked_response()
    if isinstance(result, uc.AnalysisNotFound):
        return not_found_response()
    if isinstance(result, uc.AnalysisInvalid):
        return _invalid(result)
    if isinstance(result, uc.AnalysisLegacyInvalid):
        raise ApiError(
            409,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    return ok(result.payload)


# ── Method support (wizards) ─────────────────────────────────────────────────────


@analysis_router.get("/api/assurance/guidance/{topic}")
def get_guidance(topic: str) -> JSONResponse:
    # Method coaching is static content — always callable, no store required.
    return ok(guidance_lookup(topic))


@analysis_router.get("/api/assurance/analyses/{analysis_id}/completeness")
def analysis_completeness(analysis_id: str) -> JSONResponse:
    """The completeness report for one analysis, discriminated by the analysis's own method.

    Four endpoints used to answer this — ``stpa-complete``, ``grc-complete``, ``cast-complete`` and
    ``gsn/completeness`` — each taking the analysis as an *optional* query parameter, so a caller
    could ask for a CAST report about an STPA analysis and receive an empty one that read like a
    clean bill. The method is a property of the analysis, so the server reads it rather than
    letting the URL assert it, and the response names the method it answered for.

    The argument case travels with it under ``case``: the GSN draft is built over an analysis of
    any method, so its completeness is a second view of the same analysis rather than a second
    resource. An analysis whose method defines no completeness report — FMEA, whose projection is
    its ``/matrix`` — is a typed 409 rather than an empty report.
    """
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    if not isinstance(outcome, Visible):
        return not_found_response()
    method = str(outcome.value.get("method") or "")
    report = _completeness_for_method(ctx, method, analysis_id)
    if report is None:
        raise _method_mismatch(analysis_id, method)
    _ctx, _outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    return ok({
        "analysis_id": analysis_id,
        "method": method,
        **report,
        "case": case_completeness_from_records(nodes, edges),
        "visibility_limited": visibility_limited,
    })


def _completeness_for_method(
    ctx: AssuranceContext, method: str, analysis_id: str,
) -> dict[str, object] | None:
    """The method's own report, or None where the method defines no completeness projection."""
    if method == "STPA":
        return dict(run_stpa_complete(ctx.store, analysis_id=analysis_id))
    if method == "GRC":
        return dict(run_grc_complete(ctx.store, analysis_id=analysis_id))
    if method == "CAST":
        return dict(run_cast_complete(ctx.store, ctx.archive, analysis_id=analysis_id))
    return None


def _method_mismatch(analysis_id: str, actual_method: str) -> ApiError:
    """A projection asked of an analysis whose method does not define it.

    409 rather than 404: the analysis exists and the caller may read it — what does not exist is
    this projection *of it*, and answering "not found" would send them looking for the wrong thing.
    """
    return ApiError(
        409,
        "analysis_method_mismatch",
        f"{actual_method or 'this'} analyses have no completeness projection",
        MethodMismatchDetails(
            analysis_id=analysis_id,
            expected_method="STPA, CAST or GRC",
            actual_method=actual_method,
        ),
    )


@analysis_router.get("/api/assurance/analyses/{analysis_id}/gsn/draft")
def gsn_draft(analysis_id: str) -> JSONResponse:
    ctx, outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    if not ctx.is_available():
        return locked_response()
    if not isinstance(outcome, Visible):
        return not_found_response()
    result = build_gsn_draft(
        ctx.store, analysis_id=analysis_id, visible_nodes=nodes, visible_edges=edges
    )
    if result is None:
        return not_found_response()
    return ok({
        **result,
        "publishable": bool(result["publishable"]) and not visibility_limited,
        "visibility_limited": visibility_limited,
    })


@analysis_router.get("/api/assurance/analyses/{analysis_id}/gsn/rendered")
def gsn_rendered(analysis_id: str) -> JSONResponse:
    from src.infrastructure.gui.routers import state  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_builder import (  # noqa: PLC0415
        generate_archimate_puml_body,
        render_puml_svg,
    )

    ctx, outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    if not ctx.is_available():
        return locked_response()
    if not isinstance(outcome, Visible):
        return not_found_response()
    result = build_gsn_draft(
        ctx.store, analysis_id=analysis_id, visible_nodes=nodes, visible_edges=edges
    )
    if result is None:
        return not_found_response()
    repo_root = state.maybe_engagement_root()
    if repo_root is None:
        return JSONResponse(status_code=500, content={"error": "repository_not_initialized"})
    puml = generate_archimate_puml_body(
        f"GSN {analysis_id}",
        [],
        [],
        diagram_type="gsn",
        repo_root=repo_root,
        diagram_entities=result["diagram_entities"],  # type: ignore[arg-type]
    )
    svg, warnings = render_puml_svg(puml, repo_root, "gsn")
    return ok({
        "svg": svg,
        "warnings": warnings,
        **result,
        "publishable": bool(result["publishable"]) and not visibility_limited,
        "visibility_limited": visibility_limited,
    })


@analysis_router.post("/api/assurance/analyses/{analysis_id}/gsn/publications")
def record_gsn_publication(analysis_id: str, body: RecordGsnPublicationBody) -> JSONResponse:
    from src.infrastructure.gui.routers import state  # noqa: PLC0415

    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if state.get_repo().get_diagram(body.diagram_id) is None:
        return not_found_response()
    result = run_write(lambda: record_publication(
        ctx.store,
        ctx.archive,
        analysis_id=analysis_id,
        diagram_id=body.diagram_id,
        source_bindings=[binding.model_dump() for binding in body.source_bindings],
    ))
    status = 409 if result.get("error") == "classification_not_publishable" else 200
    if result.get("error") == "analysis_not_found":
        return not_found_response()
    return JSONResponse(status_code=status, content=result, headers={"Cache-Control": NO_STORE})
