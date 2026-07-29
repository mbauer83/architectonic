"""Unlock-gated neighbor-traversal endpoint for the confidential assurance graph.

Same exposure semantics as every other assurance read (423 when locked, 404 for
absent AND above-ceiling roots, ``Cache-Control: no-store``). Size budgets and
hop clamps come from deployment settings; exceeding the wall-clock budget aborts
the whole request with a typed retryable error (503) rather than returning a
non-deterministic partial graph.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_neighbors import (
    NeighborBudgets,
    NeighborTimeBudgetExceeded,
    traverse_neighbors,
)
from src.config.assurance_settings import (
    assurance_neighbors_default_max_hops,
    assurance_neighbors_max_edges,
    assurance_neighbors_max_hops,
    assurance_neighbors_max_nodes,
    assurance_neighbors_time_budget_seconds,
)
from src.infrastructure.gui.routers._assurance_http import NO_STORE
from src.infrastructure.gui.routers._assurance_http import locked_response as _locked_response
from src.infrastructure.gui.routers._assurance_http import not_found_response as _not_found_response
from src.infrastructure.gui.routers._assurance_http import ok as _ok
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context

logger = logging.getLogger(__name__)

neighbors_router = APIRouter()


def _policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


def _effective_max_hops(requested: int | None) -> int:
    if requested is None:
        return assurance_neighbors_default_max_hops()
    return max(1, min(requested, assurance_neighbors_max_hops()))


@neighbors_router.get("/api/assurance/neighbors")
def assurance_neighbors(node_id: str, max_hops: int | None = None) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    hops = _effective_max_hops(max_hops)
    budgets = NeighborBudgets(
        max_hops=hops,
        max_nodes=assurance_neighbors_max_nodes(),
        max_edges=assurance_neighbors_max_edges(),
        time_budget_seconds=assurance_neighbors_time_budget_seconds(),
    )
    try:
        graph = traverse_neighbors(node_id, store=ctx.store, policy=pol, budgets=budgets)
    except NeighborTimeBudgetExceeded:
        logger.info("assurance_neighbors: time budget exceeded (root redacted from telemetry)")
        return JSONResponse(
            status_code=503,
            content={
                "error": "traversal_time_budget_exceeded",
                "retryable": True,
                "message": "The traversal ran past its time budget; retry, "
                           "possibly with a smaller max_hops.",
            },
            headers={"Cache-Control": NO_STORE, "Retry-After": "1"},
        )
    if graph is None:
        return _not_found_response()
    return _ok({
        "root_id": graph.root_id,
        "nodes": graph.nodes,
        "edges": graph.edges,
        "truncated": graph.truncated,
        "frontier_node_ids": graph.frontier_node_ids,
        "max_hops": hops,
        "visibility_limited": pol.scope().visibility_limited,
    })
