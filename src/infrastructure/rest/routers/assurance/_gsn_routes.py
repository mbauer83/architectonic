"""Unlock-gated HTTP endpoints for the GSN view of an analysis: draft, render, publish, read back.

Split out of ``_assurance_analysis_routes`` when that file crossed the 350-line limit, and the seam is
a real one rather than a convenience: an analysis is the aggregate, and GSN is one *view* of it —
drafted from the same nodes and edges, drawn, and then published outside the store. Nothing here
mutates the analysis.

Publishing is the one operation on this surface that leaves the confidential boundary, which is why
``publishable`` is derived rather than asserted and why a refusal carries the effective classification
that caused it.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.application.assurance.exposure import NotFound, Visible
from src.application.assurance.gsn import build_gsn_draft, list_publications, record_publication
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext
from src.infrastructure.rest.contracts.assurance_gsn import (
    GsnDraftResponse,
    GsnPublicationRecordedResponse,
    GsnRenderedResponse,
)
from src.infrastructure.rest.contracts.assurance_signals import GsnPublicationListResponse
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    ClassificationNotPublishableDetails,
    NotConfiguredDetails,
)
from src.infrastructure.rest.routers.assurance._http import (
    build_policy,
    locked_response,
    not_found_response,
    ok,
)

gsn_router = APIRouter()


class GsnPublicationBinding(BaseModel):
    assurance_node_id: str
    gsn_node_id: str


class RecordGsnPublicationBody(BaseModel):
    """The analysis is the path; the body names only what is being published."""

    model_config = ConfigDict(extra="forbid")

    diagram_id: str
    source_bindings: list[GsnPublicationBinding] = Field(default_factory=list)


def _visible_gsn_graph(
    analysis_id: str,
) -> tuple[
    AssuranceContext,
    Visible | NotFound,
    list[dict[str, object]],
    list[dict[str, object]],
    bool,
]:
    """The analysis and the graph this reader may see of it, plus whether anything was withheld.

    The withheld flag is returned rather than the count: it decides ``publishable``, and the
    cardinality of what a reader cannot see is not theirs to learn.
    """
    ctx, pol = build_policy()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    nodes, withheld = pol.filter_nodes(ctx.store.list_nodes(analysis_id=analysis_id))
    node_ids = frozenset(str(node["node_id"]) for node in nodes)
    edges = pol.filter_edges(ctx.store.list_edges(), node_ids)
    return ctx, outcome, nodes, edges, withheld > 0


@gsn_router.get("/api/assurance/analyses/{analysis_id}/gsn/draft",
    response_model=GsnDraftResponse)
def gsn_draft(analysis_id: str) -> JSONResponse:
    ctx, outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    if not ctx.is_available():
        raise locked_response()
    if not isinstance(outcome, Visible):
        raise not_found_response()
    result = build_gsn_draft(
        ctx.store, analysis_id=analysis_id, visible_nodes=nodes, visible_edges=edges
    )
    if result is None:
        raise not_found_response()
    return ok({
        **result,
        "publishable": bool(result["publishable"]) and not visibility_limited,
        "visibility_limited": visibility_limited,
    }, GsnDraftResponse)


@gsn_router.get("/api/assurance/analyses/{analysis_id}/gsn/rendered",
    response_model=GsnRenderedResponse)
def gsn_rendered(analysis_id: str) -> JSONResponse:
    from src.infrastructure.rendering.diagram_builder import (  # noqa: PLC0415
        generate_archimate_puml_body,
        render_puml_svg,
    )
    from src.infrastructure.rest.routers import state  # noqa: PLC0415

    ctx, outcome, nodes, edges, visibility_limited = _visible_gsn_graph(analysis_id)
    if not ctx.is_available():
        raise locked_response()
    if not isinstance(outcome, Visible):
        raise not_found_response()
    result = build_gsn_draft(
        ctx.store, analysis_id=analysis_id, visible_nodes=nodes, visible_edges=edges
    )
    if result is None:
        raise not_found_response()
    repo_root = state.maybe_engagement_root()
    if repo_root is None:
        raise ApiError(
            500,
            "not_configured",
            "No engagement repository is configured, so there is nothing to render against.",
            NotConfiguredDetails(
                capability="engagement-repository",
                remedy="Start the backend with an engagement repository root.",
            ),
        )
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
    }, GsnRenderedResponse)


@gsn_router.get("/api/assurance/analyses/{analysis_id}/gsn/publications",
    response_model=GsnPublicationListResponse)
def list_gsn_publications(analysis_id: str) -> JSONResponse:
    """What this analysis has been published to, read back from the bindings recording left.

    New in this release: recording a publication was possible and reading it back was not, so the
    only way to learn whether an assurance case had been published was to look at a diagram and infer
    it. 404 for an analysis the reader may not see, like every other route here — listing publications
    of something whose existence is withheld would confirm it exists.
    """
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    if not isinstance(pol.apply_analysis(ctx.store.get_analysis(analysis_id)), Visible):
        raise not_found_response()
    visible, _withheld = pol.filter_nodes(ctx.store.list_nodes())
    publications = list_publications(
        ctx.store,
        analysis_id=analysis_id,
        visible_node_ids=frozenset(str(node.get("node_id", "")) for node in visible),
    )
    return ok({
        "publications": publications,
        "visibility_limited": pol.scope().visibility_limited,
    })


@gsn_router.post("/api/assurance/analyses/{analysis_id}/gsn/publications",
    response_model=GsnPublicationRecordedResponse)
def record_gsn_publication(analysis_id: str, body: RecordGsnPublicationBody) -> JSONResponse:
    """Record that this analysis's argument has been published to a diagram.

    A refusal is the typed envelope, not a 2xx carrying ``{"error": ...}``. This route was the last one
    on the surface still answering in that older shape: a client branching on ``detail.code`` fell
    through on the one refusal this operation actually makes — an argument too sensitive to publish.
    """
    from src.infrastructure.rest.routers import state  # noqa: PLC0415

    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    if state.get_repo().get_diagram(body.diagram_id) is None:
        raise not_found_response()
    result = run_write(lambda: record_publication(
        ctx.store,
        ctx.archive,
        analysis_id=analysis_id,
        diagram_id=body.diagram_id,
        source_bindings=[binding.model_dump() for binding in body.source_bindings],
    ))
    error = result.get("error")
    if error == "analysis_not_found":
        raise not_found_response()
    if error == "classification_not_publishable":
        raise ApiError(
            409,
            "classification_not_publishable",
            "The argument reasons over content too sensitive to publish.",
            ClassificationNotPublishableDetails(
                effective_tlp=str(result.get("effective_tlp") or ""),
            ),
        )
    return ok(result, GsnPublicationRecordedResponse)
