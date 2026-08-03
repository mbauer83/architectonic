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

from typing import Literal

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance import grouping as uc
from src.application.assurance.analysis import (
    AnalysisInvalid,
    AnalysisLegacyInvalid,
    AnalysisLocked,
    AnalysisNotFound,
    AnalysisResult,
)
from src.application.assurance.exposure import AssuranceExposurePolicy, Visible
from src.application.assurance.legacy_invalid import LegacyInvalidNode
from src.application.assurance.working_set_page import analysis_working_set_page
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext
from src.infrastructure.rest.contracts.assurance_analyses import (
    AssuranceAnalysisRecord,
    AssuranceGroupListResponse,
    AssuranceGroupRecord,
    AssuranceParticipatingNodesResponse,
)
from src.infrastructure.rest.contracts.assurance_signals import AnalysisNodePageResponse
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    InvalidParticipationDetails,
    LegacyInvalidDetails,
)
from src.infrastructure.rest.routers._openapi import TAG_ASSURANCE_ANALYSES
from src.infrastructure.rest.routers.assurance._http import (
    build_policy,
    deleted,
    locked_response,
    not_found,
    not_found_response,
    ok,
    store_locked,
)
from src.infrastructure.rest.routers.assurance._invalid import invalid_as_api_error

grouping_router = APIRouter(tags=[TAG_ASSURANCE_ANALYSES])


class CreateAssuranceGroupBody(BaseModel):
    """Named for its surface, not just its shape.

    `groups.CreateGroupBody` is the repository's group create and this is the assurance store's. Two
    classes with one name make FastAPI disambiguate the published component by *module path*, so the
    wire contract read `src__infrastructure__rest__routers__groups__CreateGroupBody` — a component
    name a client cannot use and that moves whenever the Python package layout does. It moved during
    this release's regrouping, which is how it was noticed.
    """

    name: str
    description: str = ""


class FileAnalysisBody(BaseModel):
    """`group_id` is None to unfile — an analysis is worth recording before anyone settles where
    it belongs, so it has to be possible to take it back out of a group again."""

    group_id: str | None = None


def _translate(result: AnalysisResult, model: type[BaseModel] | None = None) -> JSONResponse:
    """The outcome as a response: refusals raised, the success validated against ``model``.

    ``model`` is optional because group deletion shares this translator and then discards the body for
    a 204. Every other caller passes one.
    """
    if isinstance(result, AnalysisLocked):
        raise locked_response()
    if isinstance(result, AnalysisNotFound):
        raise not_found_response()
    if isinstance(result, AnalysisInvalid):
        raise invalid_as_api_error(result)
    if isinstance(result, AnalysisLegacyInvalid):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    return ok(result.payload, model)


def _visible_analysis(
    ctx: AssuranceContext, pol: AssuranceExposurePolicy, analysis_id: str
) -> bool:
    return isinstance(pol.apply_analysis(ctx.store.get_analysis(analysis_id)), Visible)


def _visible_node_ids(ctx: AssuranceContext, pol: AssuranceExposurePolicy) -> frozenset[str]:
    visible, _withheld = pol.filter_nodes(ctx.store.list_nodes())
    return frozenset(str(node.get("node_id", "")) for node in visible)


# ── Groups ─────────────────────────────────────────────────────────────────────


@grouping_router.get("/api/assurance/groups", response_model=AssuranceGroupListResponse)
def list_groups() -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    result = uc.list_groups(ctx.store)
    return _translate(result, AssuranceGroupListResponse)


@grouping_router.post("/api/assurance/groups", status_code=200,
    response_model=AssuranceGroupRecord)
def create_group(body: CreateAssuranceGroupBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        raise locked_response()
    return _translate(run_write(lambda: uc.create_group(
        ctx.store, ctx.archive, name=body.name, description=body.description,
    )), AssuranceGroupRecord)


@grouping_router.delete("/api/assurance/groups/{group_id}", status_code=204, response_model=None)
def delete_group(group_id: str) -> Response:
    ctx = build_policy()[0]
    if not ctx.is_available():
        raise locked_response()
    return deleted(_translate(run_write(lambda: uc.delete_group(
        ctx.store, ctx.archive, group_id=group_id,
    ))))


# ── Filing ─────────────────────────────────────────────────────────────────────


@grouping_router.put("/api/assurance/analyses/{analysis_id}/group", status_code=200,
    response_model=AssuranceAnalysisRecord)
def file_analysis(analysis_id: str, body: FileAnalysisBody) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        raise not_found_response()
    # The analysis itself, re-read: filing changes the analysis record and the caller's next act is
    # to render it, so the body is the record rather than an acknowledgement of the relation.
    return _translate(run_write(lambda: uc.file_analysis(
        ctx.store, ctx.archive, analysis_id=analysis_id, group_id=body.group_id,
    )), AssuranceAnalysisRecord)


# ── Participation ──────────────────────────────────────────────────────────────


@grouping_router.get("/api/assurance/analyses/{analysis_id}/nodes",
    response_model=AnalysisNodePageResponse)
def list_analysis_nodes(
    analysis_id: str,
    relationship: Literal["authored", "referenced"] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> JSONResponse:
    """A page of the working set this analysis reasons over — authored ∪ participating.

    Paginated because an analysis's working set is unbounded: the aggregate read
    (``GET /analyses/{id}``) returns a header and role counts, and the entries come from here. Each
    item states its ``relationship`` explicitly, because a reader of a combined analysis who cannot
    tell an authored node from a borrowed one reads another method's findings as this one's.

    ``relationship`` narrows the collection rather than naming a second one: both readings are of the
    same working set, and giving each its own path would put the same rows at two addresses.
    """
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        raise not_found_response()
    page = analysis_working_set_page(
        ctx.store, pol, analysis_id, relationship=relationship, limit=limit, cursor=cursor,
    )
    return ok({
        "items": [
            {"node": item.node, "relationship": item.relationship} for item in page.items
        ],
        "next_cursor": page.next_cursor,
        "authored_total": page.authored_total,
        "referenced_total": page.referenced_total,
        "visibility_limited": pol.scope().visibility_limited,
    })


@grouping_router.get("/api/assurance/analyses/{analysis_id}/participating-nodes",
    response_model=AssuranceParticipatingNodesResponse)
def list_participating_nodes(analysis_id: str) -> JSONResponse:
    """The nodes this analysis draws on without having authored them.

    ``participating-nodes``, not ``members``: participation is directional — a node participates in
    an analysis, never the reverse — and "member" read as though the analysis owned them, which is
    what provenance means and this relation does not.
    """
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    if not _visible_analysis(ctx, pol, analysis_id):
        raise not_found_response()
    visible_ids = _visible_node_ids(ctx, pol)
    member_ids = [
        node_id for node_id in ctx.store.list_analysis_members(analysis_id)
        if node_id in visible_ids
    ]
    return ok({
        "analysis_id": analysis_id,
        "participating_node_ids": member_ids,
        "count": len(member_ids),
        "visibility_limited": pol.scope().visibility_limited,
    }, AssuranceParticipatingNodesResponse)


@grouping_router.put(
    "/api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def add_participating_node(analysis_id: str, node_id: str) -> None:
    """Assert that a node participates in this analysis. Idempotent, and 204 either way.

    ``PUT`` on the relation itself rather than ``POST`` to a collection: the relation either holds
    or it does not, so asserting it twice must be indistinguishable from asserting it once. There
    is no body — the pair *is* the request.

    A node may not participate in the analysis that authored it. That is not a duplicate to
    deduplicate away: authorship already draws the node into the analysis, and a participation row
    beside it would make the working set count it twice and let a later removal appear to detach
    something authorship still owns. Refused as ``409 invalid_participation``, with nothing written.
    """
    ctx, pol = build_policy()
    if pol.check_locked():
        raise store_locked()
    if not _visible_analysis(ctx, pol, analysis_id):
        raise not_found(f"no analysis {analysis_id!r}")
    node = pol.apply_node(ctx.store.get_node(node_id))
    if not isinstance(node, Visible):
        raise not_found(f"no node {node_id!r}")
    if str(node.value.get("analysis_id") or "") == analysis_id:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "invalid_participation",
            "a node cannot participate in the analysis that authored it",
            InvalidParticipationDetails(node_id=node_id, analysis_id=analysis_id),
        )
    _raise_for_write(run_write(lambda: uc.add_participant(
        ctx.store, ctx.archive, analysis_id=analysis_id, node_id=node_id,
    )))


@grouping_router.delete(
    "/api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def remove_participating_node(analysis_id: str, node_id: str) -> None:
    """Withdraw a participation. Idempotent, and it never touches the node or its provenance."""
    ctx, pol = build_policy()
    if pol.check_locked():
        raise store_locked()
    if not _visible_analysis(ctx, pol, analysis_id):
        raise not_found(f"no analysis {analysis_id!r}")
    if not isinstance(pol.apply_node(ctx.store.get_node(node_id)), Visible):
        raise not_found(f"no node {node_id!r}")
    _raise_for_write(run_write(lambda: uc.remove_participant(
        ctx.store, ctx.archive, analysis_id=analysis_id, node_id=node_id,
    )))


def _raise_for_write(result: AnalysisResult) -> None:
    """Turn a use-case refusal into the shared envelope. A success says nothing, which is the point
    of a 204 — the relation now holds, and there is no further fact to report."""
    if isinstance(result, AnalysisLocked):
        raise store_locked()
    if isinstance(result, AnalysisNotFound):
        raise not_found(f"no such record: {result.analysis_id}")
    if isinstance(result, AnalysisLegacyInvalid):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    if isinstance(result, AnalysisInvalid):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "bad_request", result.message)
