"""Unlock-gated HTTP read endpoints for the confidential assurance store.

All endpoints share one pattern:
  1. Build an AssuranceExposurePolicy from the current context.
  2. Check locked → 423 with Cache-Control: no-store.
  3. Fetch from the store/archive/connector.
  4. Apply the policy (filter, redact, apply_node).
  5. Return with Cache-Control: no-store.

Response semantics (per the AssuranceExposurePolicy contract):
  - Locked store           → 423 Locked
  - Collection reads       → omit above-ceiling records; visibility_limited flag
  - Direct read (/nodes/:id) → 404 for absent AND above-ceiling (indistinguishable)
  - HTTP 403               → never on reads (would disclose existence)
  - All responses          → Cache-Control: no-store
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from src.application.assurance.edge_enrichment import enrich_edges, visible_nodes_by_id
from src.application.assurance.exposure import AssuranceExposurePolicy, Visible
from src.application.assurance.fmea_lens import failure_mode_summary
from src.application.assurance.node_degrees import with_degrees
from src.application.assurance.node_sorting import MOST_RECENTLY_UPDATED_FIRST
from src.application.assurance.provenance import analyses_by_id, author_of, provenance
from src.application.assurance.queries import coverage_gaps, risk_register
from src.domain.artifact_id import canonical_entity_key
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context
from src.infrastructure.rest.contracts.assurance_nodes import (
    AssuranceEdgeListResponse,
    AssuranceNodeDetailResponse,
    AssuranceNodeListResponse,
)
from src.infrastructure.rest.contracts.assurance_queries import (
    AssuranceBaselineListResponse,
    AssuranceCoverageResponse,
    AssuranceRiskRegisterResponse,
    AssuranceSearchResponse,
    AssuranceStatsResponse,
    AssuranceVerifyResponse,
)
from src.infrastructure.rest.contracts.assurance_signals import ArchLensResponse
from src.infrastructure.rest.routers.assurance._http import locked_response as _locked_response
from src.infrastructure.rest.routers.assurance._http import not_found_response as _not_found_response
from src.infrastructure.rest.routers.assurance._http import ok as _ok

logger = logging.getLogger(__name__)

read_router = APIRouter()

_NO_STORE = "no-store"


def _policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


# ── Search ────────────────────────────────────────────────────────────────────

def _assurance_hit(
    node: dict[str, object],
    analyses_by_id: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Shape a visible assurance node into the standard SearchHit envelope.

    Content snippets are intentionally excluded — they may contain classified text.

    The authoring analysis travels with the hit, because the surface that consumes this searches
    across the whole store on purpose: an FMEA's edge picker has to reach the hazard an STPA
    identified, and a candidate list of bare names gives the author no way to tell whose work they
    are reaching for. `author_of` resolves it against the analyses this reader may see, so a node
    whose analysis is above the ceiling reports none rather than naming it.
    """
    return {
        "score": 1.0,
        "record_type": "assurance-node",
        "artifact_id": str(node["node_id"]),
        "name": str(node.get("name", "")),
        "artifact_type": str(node.get("node_type", "")),
        "status": str(node.get("status", "")),
        "path": "",
        "analysis": author_of(node, analyses_by_id),
    }


@read_router.get("/api/assurance/search", response_model=AssuranceSearchResponse)
def search_assurance_nodes(
    q: str,
    limit: int = Query(default=20, le=100),
) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    if not q.strip():
        return _ok({"query": q, "hits": [], "count": 0}, AssuranceSearchResponse)
    raw = ctx.store.search_nodes(q.strip(), limit=limit * 2)
    visible, _ = pol.filter_nodes(raw)
    visible_analyses, _ = pol.filter_analyses(ctx.store.list_analyses())
    by_id = analyses_by_id(visible_analyses)
    hits = [_assurance_hit(n, by_id) for n in visible[:limit]]
    logger.info("assurance_search: ceiling=%s hits=%d (redacted telemetry)", pol.scope().ceiling, len(hits))
    return _ok({"query": q, "hits": hits, "count": len(hits)}, AssuranceSearchResponse)


# ── Nodes ─────────────────────────────────────────────────────────────────────

@read_router.get("/api/assurance/nodes", response_model=AssuranceNodeListResponse)
def list_assurance_nodes(
    node_type: str | None = None,
    status: str | None = None,
    concern_class: str | None = None,
    tlp: str | None = None,
    binding_status: str | None = None,
    analysis_id: str | None = None,
    sort: str = MOST_RECENTLY_UPDATED_FIRST[0],
    order: str = MOST_RECENTLY_UPDATED_FIRST[1],
    response: Response = Response(),
) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    # Ordered by the store, ahead of the exposure filter below: filtering preserves the
    # relative order of what survives, so sorting can neither change which nodes a reader
    # sees nor reveal the withheld count.
    nodes = ctx.store.list_nodes(
        node_type=node_type,
        status=status,
        concern_class=concern_class,
        tlp=tlp,
        analysis_id=analysis_id,
        sort=sort,
        order=order,
    )
    if binding_status:
        nodes = [n for n in nodes if str(n.get("binding_status", "")) == binding_status]
    visible, withheld = pol.filter_nodes(nodes)
    scope = pol.scope()
    if withheld:
        logger.info("list_nodes: ceiling=%s returned=%d withheld=%d", scope.ceiling, len(visible), withheld)
    # Degrees over the policy-filtered edge set, never the raw one: a count taken before the
    # filter would publish the existence of above-ceiling neighbours. See
    # `assurance_node_degrees`.
    visible_ids = frozenset(str(n.get("node_id", "")) for n in visible)
    visible_edges = pol.filter_edges(ctx.store.list_edges(), visible_ids)
    return _ok({
        "nodes": with_degrees(visible, visible_edges),
        "count": len(visible),
        "visibility_limited": scope.visibility_limited,
    }, AssuranceNodeListResponse)


@read_router.get("/api/assurance/nodes/{node_id}", response_model=AssuranceNodeDetailResponse)
def read_assurance_node(node_id: str) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    node = ctx.store.get_node(node_id)
    outcome = pol.apply_node(node)
    if not isinstance(outcome, Visible):
        raise _not_found_response()
    visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes())
    nodes_by_id = visible_nodes_by_id(visible_nodes)
    nodes_by_id[node_id] = outcome.value
    all_visible = frozenset(nodes_by_id)
    edges_out = ctx.store.list_edges(source_id=node_id)
    edges_in = ctx.store.list_edges(target_id=node_id)
    arch_refs = ctx.store.list_arch_refs(assurance_node_id=node_id)
    visible_analyses, _ = pol.filter_analyses(ctx.store.list_analyses())
    return _ok({
        "node": outcome.value,
        "outgoing_edges": enrich_edges(pol.filter_edges(edges_out, all_visible), nodes_by_id),
        "incoming_edges": enrich_edges(pol.filter_edges(edges_in, all_visible), nodes_by_id),
        "arch_refs": arch_refs,
        # Authorship and participation, resolved against the analyses this reader may see — a
        # borrowed entity has to look borrowed. See `assurance_provenance`.
        **provenance(
            outcome.value,
            participating_analysis_ids=ctx.store.list_participating_analyses(node_id),
            visible_analyses=visible_analyses,
        ),
        "visibility_limited": pol.scope().visibility_limited,
    }, AssuranceNodeDetailResponse)


# ── Edges ─────────────────────────────────────────────────────────────────────

@read_router.get("/api/assurance/edges", response_model=AssuranceEdgeListResponse)
def list_assurance_edges(
    source_id: str | None = None,
    target_id: str | None = None,
    conn_type: str | None = None,
) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    edges = ctx.store.list_edges(source_id=source_id, target_id=target_id, conn_type=conn_type)
    visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes())
    nodes_by_id = visible_nodes_by_id(visible_nodes)
    filtered = enrich_edges(pol.filter_edges(edges, frozenset(nodes_by_id)), nodes_by_id)
    return _ok(
        {"edges": filtered, "count": len(filtered), "visibility_limited": pol.scope().visibility_limited},
        AssuranceEdgeListResponse,
    )


# ── Aggregates ────────────────────────────────────────────────────────────────

@read_router.get("/api/assurance/stats", response_model=AssuranceStatsResponse)
def assurance_stats() -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    visible, _ = pol.filter_nodes(ctx.store.list_nodes())
    all_edges = ctx.store.list_edges()
    return _ok(pol.redact_stats(visible, all_edges), AssuranceStatsResponse)


@read_router.get("/api/assurance/coverage", response_model=AssuranceCoverageResponse)
def assurance_coverage() -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    visible, _ = pol.filter_nodes(ctx.store.list_nodes())
    visible_ids = frozenset(str(n["node_id"]) for n in visible)
    all_edges = ctx.store.list_edges()
    visible_edges = pol.filter_edges(all_edges, visible_ids)
    return _ok(coverage_gaps(visible, visible_edges), AssuranceCoverageResponse)


@read_router.get("/api/assurance/verify", response_model=AssuranceVerifyResponse)
def assurance_verify() -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    from src.application.verification.assurance_verifier import format_result, verify_store  # noqa: PLC0415
    visible, _ = pol.filter_nodes(ctx.store.list_nodes())
    visible_ids = frozenset(str(n["node_id"]) for n in visible)
    result = pol.redact_verification(
        verify_store(ctx.store, basis=current_architecture_basis()), visible_ids
    )
    return _ok(
        {**format_result(result), "visibility_limited": pol.scope().visibility_limited},
        AssuranceVerifyResponse,
    )


@read_router.get("/api/assurance/risk-register", response_model=AssuranceRiskRegisterResponse)
def assurance_risk_register() -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    visible, _ = pol.filter_nodes(ctx.store.list_nodes())
    visible_ids = frozenset(str(n["node_id"]) for n in visible)
    visible_edges = pol.filter_edges(ctx.store.list_edges(), visible_ids)
    return _ok(risk_register(visible, visible_edges), AssuranceRiskRegisterResponse)


# ── Baselines ─────────────────────────────────────────────────────────────────

@read_router.get("/api/assurance/baselines", response_model=AssuranceBaselineListResponse)
def list_baselines() -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        raise _locked_response()
    baselines = ctx.archive.list_baselines()
    return _ok(
        {"baselines": baselines, "count": len(baselines)}, AssuranceBaselineListResponse,
    )


# ── Architecture lens: assurance findings about one architecture element ─────

@read_router.get("/api/assurance/arch-artifacts/{arch_artifact_id}/lens",
    summary="Assurance findings about one architecture artifact", response_model=ArchLensResponse,
    response_model_exclude_unset=True)
def arch_lens(arch_artifact_id: str) -> dict[str, Any]:
    """Return assurance nodes that concern a given architecture artifact.

    Used by EntityDetailView / DiagramDetailView to show the assurance lens.
    Returns an empty result (not 404) when no references exist or store is locked,
    so the UI can distinguish locked from empty from truly unlocked.

    The id is canonicalised on the way in: the GUI navigates by the full slugged id while the
    store keys references on the stable form, and the filter below is an exact match. Compared
    raw, an element with assurance findings shows none.
    """
    ctx, pol = _policy()
    element_key = canonical_entity_key(arch_artifact_id)
    if pol.check_locked():
        return {
            "arch_artifact_id": arch_artifact_id,
            "locked": True,
            "nodes": [],
            "count": 0,
        }
    refs = ctx.store.list_arch_refs(arch_artifact_id=element_key)
    node_ids = {str(r["assurance_node_id"]) for r in refs}
    all_nodes = ctx.store.list_nodes()
    matched = [n for n in all_nodes if str(n["node_id"]) in node_ids]
    visible, _ = pol.filter_nodes(matched)
    scope = pol.scope()
    return {
        "arch_artifact_id": arch_artifact_id,
        "locked": False,
        "nodes": visible,
        "count": len(visible),
        "visibility_limited": scope.visibility_limited,
        "failure_mode_summary": failure_mode_summary(
            arch_artifact_id, store=ctx.store, policy=pol, nodes=all_nodes,
            basis=current_architecture_basis(),
        ),
    }
