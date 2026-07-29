"""Unlock-gated HTTP endpoints for the diagrams projected from the live assurance store.

Both routes are scoped to one analysis, because a derived diagram belongs to a unit of work rather
than to the store: there is one control structure per STPA and one matrix per FMEA. Rendering a
type with no analysis named draws every analysis at once, which is nothing coherent and was what
"diagram rendering is unavailable" reported.

  GET /api/assurance/diagrams
      One entry per visible analysis per applicable type, titled for the analysis.
  GET /api/assurance/analyses/{analysis_id}/diagrams/{diagram_type}/rendered
      That analysis' projection of that type: PUML, SVG, and the projected nodes and edges.

The graph a projection sees is the analysis' working set — what it authored plus what it borrowed
(see `assurance_working_set`), already exposure-filtered. An above-ceiling analysis is 404, and a
type the analysis' method does not draw is 404 with the applicable types named: asking an STPA for
an FMEA matrix is a mistake worth reporting, not an empty grid.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.application.assurance_diagrams import (
    assurance_surface_diagrams,
    diagram_types_for_method,
)
from src.application.assurance_exposure import Visible
from src.application.assurance_working_set import analysis_working_set
from src.diagram_types._assurance_puml_alias import safe_alias
from src.domain.ontology_representation.ontology_protocol import (
    NodeRepresentingEdgeRenderer,
    StoreGraphProjectingDiagramType,
)
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog
from src.infrastructure.gui.routers._assurance_http import (
    NO_STORE,
    build_policy,
    locked_response,
    not_found_response,
    ok,
)

logger = logging.getLogger(__name__)

diagram_router = APIRouter()


def _assurance_diagram_type(diagram_type: str) -> StoreGraphProjectingDiagramType | None:
    """The registered diagram type for a live assurance projection, or None if there is no such type.

    Resolved against the COMPLETE vocabulary, not the active registry: which diagram types exist, and
    how each is drawn, cannot depend on whether the confidential-store capability happens to be
    configured on this host — and this endpoint has already refused a locked store before reaching
    here. Same reasoning as the confidentiality routing, which classifies assurance diagram types
    from the complete registry for the same reason.

    A type that cannot project a store graph is not servable here, whatever else it can do.
    """
    registered = complete_diagram_type_catalog().find_diagram_type(diagram_type)
    if registered is None:
        return None
    if not isinstance(registered, StoreGraphProjectingDiagramType):
        logger.warning("Assurance diagram %s: diagram type cannot project a store graph", diagram_type)
        return None
    return registered


def _render_diagram_type(
    diagram_type: StoreGraphProjectingDiagramType,
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> tuple[str | None, list[dict[str, str]]]:
    """Render a projection through its diagram type, and report which edges stand for a node.

    The read layer holds no notation of its own: a live projection and a persisted diagram of the
    same type are drawn by the same code. Both extras are optional capabilities — a type whose grid
    is built client-side raises rather than emitting PUML, and a notation that draws every node as a
    shape offers no edge↔node mapping.
    """
    payload: dict[str, object] = {"nodes": nodes, "edges": edges}
    renderer = diagram_type.renderer  # type: ignore[attr-defined]
    try:
        puml: str | None = renderer.render_body("", [], [], "", Path(), diagram_entities=payload)
    except ValueError:
        puml = None
    representatives = (
        renderer.node_representing_edges(diagram_entities=payload)
        if isinstance(renderer, NodeRepresentingEdgeRenderer)
        else []
    )
    return puml, representatives


def _render_svg(puml: str, label: str) -> str | None:
    try:
        from src.infrastructure.gui.routers import state as s  # noqa: PLC0415
        from src.infrastructure.rendering.diagram_builder import render_puml_svg  # noqa: PLC0415

        repo_root = s.maybe_engagement_root()
        if repo_root is None:
            logger.warning("Assurance diagram %s: no engagement root; SVG skipped", label)
            return None
        svg_text, messages = render_puml_svg(puml, repo_root, label)
        if svg_text is None and messages:
            logger.warning("Assurance diagram %s render produced no SVG: %s", label, "; ".join(messages))
        return svg_text
    except Exception:  # noqa: BLE001
        logger.exception("Assurance diagram %s SVG render failed", label)
        return None


@diagram_router.get("/api/assurance/diagrams")
def list_assurance_diagrams() -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    # Filtered before the catalog is built, not after: an entry names its analysis, so an
    # above-ceiling analysis appearing here would disclose both its existence and its method.
    visible_analyses, _withheld = pol.filter_analyses(ctx.store.list_analyses())
    diagrams = assurance_surface_diagrams(complete_diagram_type_catalog(), visible_analyses)
    return ok({
        "diagrams": diagrams,
        "count": len(diagrams),
        "visibility_limited": pol.scope().visibility_limited,
    })


@diagram_router.get("/api/assurance/analyses/{analysis_id}/diagrams/{diagram_type}/rendered")
def render_assurance_diagram(analysis_id: str, diagram_type: str) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()

    analysis = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    if not isinstance(analysis, Visible):
        return not_found_response()
    method = str(analysis.value.get("method", ""))
    applicable = diagram_types_for_method(complete_diagram_type_catalog(), method)

    registered = _assurance_diagram_type(diagram_type)
    if registered is None or diagram_type not in applicable:
        return JSONResponse(
            status_code=404,
            content={
                "error": "unknown_diagram_type",
                "diagram_type": diagram_type,
                "analysis_id": analysis_id,
                "method": method,
                "available": applicable,
            },
            headers={"Cache-Control": NO_STORE},
        )

    working_set = analysis_working_set(ctx.store, pol, analysis_id)
    # Which nodes take part and which edges are admitted is the diagram type's own knowledge, so
    # this surface asks rather than branching per type. A type that draws no PUML (the UCA grid is
    # built client-side from these nodes and edges) simply declines to render.
    projected_nodes, projected_edges = registered.project_store_graph(
        working_set.nodes, working_set.edges
    )
    puml, node_representing_edges = _render_diagram_type(registered, projected_nodes, projected_edges)
    svg = _render_svg(puml, diagram_type) if puml is not None else None

    return ok({
        "diagram_id": f"{analysis_id}::{diagram_type}",
        "analysis_id": analysis_id,
        "analysis_name": str(analysis.value.get("name", "")),
        "diagram_type": diagram_type,
        "puml": puml,
        "svg": svg,
        "nodes": projected_nodes,
        "edges": projected_edges,
        # Which of these the analysis authored, so a borrowed node can be drawn as borrowed rather
        # than passing for native. See `assurance_provenance` for the same distinction on a node.
        "authored_node_ids": sorted(
            node_id for node_id in working_set.authored_node_ids
            if node_id in {str(n["node_id"]) for n in projected_nodes}
        ),
        # The alias each node is drawn under, so the viewer can map a rendered shape back to a node
        # by looking it up rather than by re-deriving the naming rule. The rule belongs to whatever
        # wrote the PUML; a client that reconstructs it is a second implementation of a contract
        # across a language boundary, and the two drifted silently once already — every shape in a
        # bowtie was inert because one side prefixed the alias and the other did not.
        "node_aliases": {
            safe_alias(str(node["node_id"])): str(node["node_id"]) for node in projected_nodes
        },
        # Drawn edges that stand for a node (a control action is rendered as its arrow), so a
        # click on one selects that node instead of doing nothing.
        "node_representing_edges": node_representing_edges,
        "visibility_limited": pol.scope().visibility_limited,
    })
