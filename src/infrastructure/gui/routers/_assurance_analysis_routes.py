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
from pydantic import BaseModel, Field

from src.application import assurance_analysis as uc
from src.application.assurance_exposure import NotFound, Visible
from src.application.assurance_gsn import build_gsn_draft, record_publication
from src.application.assurance_guidance import lookup as guidance_lookup
from src.application.verification.case_draft import case_completeness_from_records
from src.application.verification.cast_complete import run_cast_complete
from src.application.verification.grc_complete import run_grc_complete
from src.application.verification.stpa_complete import run_stpa_complete
from src.infrastructure.assurance.write_serialization import run_write
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
    analysis_id: str
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
    return ok(result.payload)


# ── Method support (wizards) ─────────────────────────────────────────────────────


@analysis_router.get("/api/assurance/guidance")
def get_guidance(topic: str) -> JSONResponse:
    # Method coaching is static content — always callable, no store required.
    return ok(guidance_lookup(topic))


@analysis_router.get("/api/assurance/stpa-complete")
def stpa_complete(analysis_id: str | None = None) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    return ok(run_stpa_complete(ctx.store, analysis_id=analysis_id))


@analysis_router.get("/api/assurance/grc-complete")
def grc_complete(analysis_id: str | None = None) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    return ok(run_grc_complete(ctx.store, analysis_id=analysis_id))


@analysis_router.get("/api/assurance/cast-complete")
def cast_complete(analysis_id: str | None = None) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    return ok(run_cast_complete(ctx.store, ctx.archive, analysis_id=analysis_id))


@analysis_router.get("/api/assurance/gsn/draft")
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


@analysis_router.get("/api/assurance/gsn/rendered")
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


@analysis_router.get("/api/assurance/gsn/completeness")
def gsn_completeness(analysis_id: str) -> JSONResponse:
    ctx, outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    if not ctx.is_available():
        return locked_response()
    if not isinstance(outcome, Visible):
        return not_found_response()
    return ok({
        **case_completeness_from_records(nodes, edges),
        "visibility_limited": visibility_limited,
    })


@analysis_router.post("/api/assurance/gsn/publications")
def record_gsn_publication(body: RecordGsnPublicationBody) -> JSONResponse:
    from src.infrastructure.gui.routers import state  # noqa: PLC0415

    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if state.get_repo().get_diagram(body.diagram_id) is None:
        return not_found_response()
    result = run_write(lambda: record_publication(
        ctx.store,
        ctx.archive,
        analysis_id=body.analysis_id,
        diagram_id=body.diagram_id,
        source_bindings=[binding.model_dump() for binding in body.source_bindings],
    ))
    status = 409 if result.get("error") == "classification_not_publishable" else 200
    if result.get("error") == "analysis_not_found":
        return not_found_response()
    return JSONResponse(status_code=status, content=result, headers={"Cache-Control": NO_STORE})
