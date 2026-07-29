"""Unlock-gated HTTP endpoints for filing analyses and recording participation.

Filing puts an analysis in a group; participation draws a node into an analysis that did not
author it. Both are exposed here rather than folded into the analysis routes, because both are
relations *between* aggregates and neither changes the analysis or the node itself.

Exposure, in the terms `AssuranceExposurePolicy` already sets:

* An above-ceiling analysis or node is **404 on every one of these routes**, reads and writes
  alike. Filing something a reader cannot see would confirm it exists.
* A member list is filtered to the nodes the reader may see, and a node's participation is
  filtered to the analyses the reader may see. `list_analysis_members` reports the membership as
  stored, which includes rows a given reader has no business knowing about — the same reason
  `assurance_node_degrees` counts inside the exposure boundary rather than outside it.
* A group carries no classification of its own: it is a name and a description, and the store's
  ceiling governs the analyses inside it. So there is nothing to filter on a group record, and
  the group list is returned as stored.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application import assurance_grouping as uc
from src.application.assurance_analysis import (
    AnalysisInvalid,
    AnalysisLocked,
    AnalysisNotFound,
    AnalysisResult,
)
from src.application.assurance_exposure import AssuranceExposurePolicy, Visible
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.routers._assurance_http import (
    NO_STORE,
    build_policy,
    locked_response,
    not_found_response,
    ok,
)
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

grouping_router = APIRouter()


class CreateGroupBody(BaseModel):
    name: str
    description: str = ""


class FileAnalysisBody(BaseModel):
    """`group_id` is None to unfile — an analysis is worth recording before anyone settles where
    it belongs, so it has to be possible to take it back out of a group again."""

    group_id: str | None = None


class AddMemberBody(BaseModel):
    node_id: str


def _translate(result: AnalysisResult) -> JSONResponse:
    if isinstance(result, AnalysisLocked):
        return locked_response()
    if isinstance(result, AnalysisNotFound):
        return not_found_response()
    if isinstance(result, AnalysisInvalid):
        return JSONResponse(
            status_code=400,
            content={"error": result.error, "message": result.message},
            headers={"Cache-Control": NO_STORE},
        )
    return ok(result.payload)


def _visible_analysis(
    ctx: AssuranceContext, pol: AssuranceExposurePolicy, analysis_id: str
) -> bool:
    return isinstance(pol.apply_analysis(ctx.store.get_analysis(analysis_id)), Visible)


def _visible_node_ids(ctx: AssuranceContext, pol: AssuranceExposurePolicy) -> frozenset[str]:
    visible, _withheld = pol.filter_nodes(ctx.store.list_nodes())
    return frozenset(str(node.get("node_id", "")) for node in visible)


# ── Groups ─────────────────────────────────────────────────────────────────────


@grouping_router.get("/api/assurance/groups")
def list_groups() -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    result = uc.list_groups(ctx.store)
    return _translate(result)


@grouping_router.post("/api/assurance/groups", status_code=200)
def create_group(body: CreateGroupBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        return locked_response()
    return _translate(run_write(lambda: uc.create_group(
        ctx.store, ctx.archive, name=body.name, description=body.description,
    )))


@grouping_router.delete("/api/assurance/groups/{group_id}", status_code=200)
def delete_group(group_id: str) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        return locked_response()
    return _translate(run_write(lambda: uc.delete_group(
        ctx.store, ctx.archive, group_id=group_id,
    )))


# ── Filing ─────────────────────────────────────────────────────────────────────


@grouping_router.put("/api/assurance/analyses/{analysis_id}/group", status_code=200)
def file_analysis(analysis_id: str, body: FileAnalysisBody) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        return not_found_response()
    return _translate(run_write(lambda: uc.file_analysis(
        ctx.store, ctx.archive, analysis_id=analysis_id, group_id=body.group_id,
    )))


# ── Participation ──────────────────────────────────────────────────────────────


@grouping_router.get("/api/assurance/analyses/{analysis_id}/members")
def list_members(analysis_id: str) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        return not_found_response()
    visible_ids = _visible_node_ids(ctx, pol)
    member_ids = [
        node_id for node_id in ctx.store.list_analysis_members(analysis_id)
        if node_id in visible_ids
    ]
    return ok({
        "analysis_id": analysis_id,
        "member_node_ids": member_ids,
        "count": len(member_ids),
        "visibility_limited": pol.scope().visibility_limited,
    })


@grouping_router.post("/api/assurance/analyses/{analysis_id}/members", status_code=200)
def add_member(analysis_id: str, body: AddMemberBody) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        return not_found_response()
    if not isinstance(pol.apply_node(ctx.store.get_node(body.node_id)), Visible):
        return not_found_response()
    return _translate(run_write(lambda: uc.add_participant(
        ctx.store, ctx.archive, analysis_id=analysis_id, node_id=body.node_id,
    )))


@grouping_router.delete(
    "/api/assurance/analyses/{analysis_id}/members/{node_id}", status_code=200
)
def remove_member(analysis_id: str, node_id: str) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        return locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        return not_found_response()
    if not isinstance(pol.apply_node(ctx.store.get_node(node_id)), Visible):
        return not_found_response()
    return _translate(run_write(lambda: uc.remove_participant(
        ctx.store, ctx.archive, analysis_id=analysis_id, node_id=node_id,
    )))
