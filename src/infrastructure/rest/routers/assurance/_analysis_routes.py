"""Unlock-gated HTTP endpoints for the assurance analysis aggregate + STPA method.

An analysis is the aggregate root for a unit of STPA/CAST/GRC work. Reads are
exposure-filtered (above-ceiling analyses are omitted from lists and 404 on direct
read); writes go through the application use cases (audited). Also hosts the
method-support endpoints the wizards call: per-step guidance (always callable) and
analysis-scoped STPA completeness.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance import analysis as uc
from src.application.assurance.exposure import NotFound, Visible
from src.application.assurance.guidance import lookup as guidance_lookup
from src.application.assurance.legacy_invalid import LegacyInvalidNode
from src.application.verification.case_draft import case_completeness_from_records
from src.application.verification.cast_complete import run_cast_complete
from src.application.verification.grc_complete import run_grc_complete
from src.application.verification.stpa_complete import run_stpa_complete
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext
from src.infrastructure.rest.contracts.assurance_analyses import (
    AssuranceAnalysisDetailResponse,
    AssuranceAnalysisListResponse,
    AssuranceAnalysisRecord,
    AssuranceGuidanceResponse,
)
from src.infrastructure.rest.contracts.assurance_queries import (
    AssuranceAnalysisCompletenessResponse,
)
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    LegacyInvalidDetails,
    MethodMismatchDetails,
    UnknownGuidanceTopicDetails,
)
from src.infrastructure.rest.routers._openapi import TAG_ASSURANCE_ANALYSES
from src.infrastructure.rest.routers.assurance._http import (
    build_policy,
    deleted,
    locked_response,
    not_found_response,
    ok,
)
from src.infrastructure.rest.routers.assurance._invalid import invalid_as_api_error

analysis_router = APIRouter(tags=[TAG_ASSURANCE_ANALYSES])


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


def _invalid(result: uc.AnalysisInvalid) -> ApiError:
    """The refusal, in the shared envelope — **raised**, not returned.

    The mapping lives in ``_assurance_invalid`` so both routers translate the same way and a code with
    no mapping fails loudly rather than reaching a client as an undeclared string.
    """
    return invalid_as_api_error(result)


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


@analysis_router.get("/api/assurance/analyses", response_model=AssuranceAnalysisListResponse)
def list_analyses(method: str | None = None, status: str | None = None) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    analyses = ctx.store.list_analyses(method=method, status=status)
    visible, _withheld = pol.filter_analyses(analyses)
    scope = pol.scope()
    return ok({
        "analyses": visible,
        "count": len(visible),
        "visibility_limited": scope.visibility_limited,
    }, AssuranceAnalysisListResponse)


@analysis_router.get("/api/assurance/analyses/{analysis_id}",
    response_model=AssuranceAnalysisDetailResponse)
def get_analysis(analysis_id: str) -> JSONResponse:
    ctx, pol = build_policy()
    if pol.check_locked():
        raise locked_response()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    if isinstance(outcome, Visible):
        # Visible node count scoped to this analysis (exposure-filtered).
        visible_nodes, _ = pol.filter_nodes(ctx.store.list_nodes(analysis_id=analysis_id))
        return ok(
            {"analysis": outcome.value, "node_count": len(visible_nodes)},
            AssuranceAnalysisDetailResponse,
        )
    raise not_found_response()


# ── Writes ──────────────────────────────────────────────────────────────────────


@analysis_router.post("/api/assurance/analyses", status_code=200,
    response_model=AssuranceAnalysisRecord)
def create_analysis(body: CreateAnalysisBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        raise locked_response()
    result = run_write(lambda: uc.create_analysis(
        ctx.store, ctx.archive,
        name=body.name, method=body.method,
        architecture_anchor_id=body.architecture_anchor_id,
        tlp=body.tlp, status=body.status,
    ))
    return _translate_write(result, AssuranceAnalysisRecord)


@analysis_router.patch("/api/assurance/analyses/{analysis_id}", status_code=200,
    response_model=AssuranceAnalysisRecord)
def update_analysis(analysis_id: str, body: UpdateAnalysisBody) -> JSONResponse:
    ctx = build_policy()[0]
    if not ctx.is_available():
        raise locked_response()
    result = run_write(lambda: uc.update_analysis(
        ctx.store, ctx.archive,
        analysis_id=analysis_id,
        name=body.name, status=body.status, tlp=body.tlp,
    ))
    return _translate_write(result, AssuranceAnalysisRecord)


@analysis_router.delete("/api/assurance/analyses/{analysis_id}", status_code=204, response_model=None)
def delete_analysis(analysis_id: str) -> Response:
    ctx = build_policy()[0]
    if not ctx.is_available():
        raise locked_response()
    result = run_write(lambda: uc.delete_analysis(
        ctx.store, ctx.archive, analysis_id=analysis_id,
    ))
    return deleted(_translate_write(result))


def _translate_write(
    result: uc.AnalysisResult, model: type[BaseModel] | None = None
) -> JSONResponse:
    """The write's outcome as a response: the refusals raised, the success validated against ``model``.

    ``model`` is optional because the deletion path shares this translator and then discards the body
    for a 204 — there is nothing to hold to a contract. Every other caller passes one, so a payload key
    the DTO does not declare fails here rather than reaching a client promised otherwise.
    """
    if isinstance(result, uc.AnalysisLocked):
        raise locked_response()
    if isinstance(result, uc.AnalysisNotFound):
        raise not_found_response()
    if isinstance(result, uc.AnalysisInvalid):
        raise _invalid(result)
    if isinstance(result, uc.AnalysisLegacyInvalid):
        raise ApiError(
            409,
            "node_legacy_invalid",
            LegacyInvalidNode(node_id=result.node_id).message,
            LegacyInvalidDetails(
                node_id=result.node_id, permitted_operation=result.permitted_operation
            ),
        )
    return ok(result.payload, model)


# ── Method support (wizards) ─────────────────────────────────────────────────────


@analysis_router.get("/api/assurance/guidance/{topic}", response_model=AssuranceGuidanceResponse)
def get_guidance(topic: str) -> JSONResponse:
    """Method coaching for one topic. Static content, so this is callable with the store locked.

    An unrecognised topic is a 404 carrying the topics that do exist, not a 200 whose body says no
    guidance was found. The catalogue is fixed and the topic is a path segment, so an unknown one names
    no resource — and the 200 made every caller read the body to discover whether it had an answer.
    """
    found = guidance_lookup(topic)
    # `available_topics` is present only on the miss branch of `guidance_lookup`, which is how the
    # lookup reports that nothing matched — it has no other way to say so.
    available = found.get("available_topics")
    if isinstance(available, list):
        raise ApiError(
            404,
            "unknown_guidance_topic",
            f"No guidance for {topic!r}.",
            UnknownGuidanceTopicDetails(
                topic=topic, available_topics=[str(name) for name in available],
            ),
        )
    return ok(found, AssuranceGuidanceResponse)


@analysis_router.get("/api/assurance/analyses/{analysis_id}/completeness",
    response_model=AssuranceAnalysisCompletenessResponse)
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
        raise locked_response()
    outcome = pol.apply_analysis(ctx.store.get_analysis(analysis_id))
    if not isinstance(outcome, Visible):
        raise not_found_response()
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
    }, AssuranceAnalysisCompletenessResponse)


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
