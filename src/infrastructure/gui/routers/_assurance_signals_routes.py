"""Security-posture REST surface: metrics over the active signal snapshot and the
audited VEX mutation route. Reads are unlock-gated with no-store semantics and
exposure-filtered before aggregation; VEX writes pass the signal-mutation
capability gate (typed denial) and land data + audit in one transaction."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.security_signals.capability import SignalMutationDenied
from src.application.security_signals.metrics import compute_security_metrics
from src.application.security_signals.read_token import AvailabilityState, evaluate_pinned
from src.application.security_signals.vex import (
    RecordVexRequest,
    VexInvalid,
    record_vex_assessment,
)
from src.infrastructure.assurance.signal_gate import current_signal_mutation_capability
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.gui.routers._assurance_http import locked_response as _locked_response
from src.infrastructure.gui.routers._assurance_http import ok as _ok
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context

signals_router = APIRouter()

_NO_STORE = "no-store"


def _policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


@signals_router.get("/api/assurance/security-metrics")
def security_metrics(anchor_entity_id: str) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    snapshot_store = ctx.snapshot_store
    vex_store = ctx.vex_store
    if snapshot_store is None or vex_store is None:
        return _ok({
            "availability": "unavailable",
            "reason": "metrics require the SQLCipher store with co-located signals",
        })
    if not isinstance(ctx.store, AvailabilityState):
        metrics = compute_security_metrics(
            anchor_entity_id, snapshot_store=snapshot_store, vex_store=vex_store, policy=pol,
        )
        return _ok(asdict(metrics))
    # Snapshot pinning: the whole read batch happens under one token; any
    # activation / lock cycle / ceiling / VEX change mid-evaluation yields
    # unavailable/retry — never values mixing two snapshots.
    result, _token = evaluate_pinned(
        anchor_entity_id,
        availability=ctx.store,
        snapshot_store=snapshot_store,
        vex_store=vex_store,
        exposure_ceiling=ctx.max_classification,
        evaluate=lambda: compute_security_metrics(
            anchor_entity_id, snapshot_store=snapshot_store, vex_store=vex_store, policy=pol,
        ),
    )
    if result is None:
        return _ok({"availability": "unavailable", "reason": "snapshot changed mid-evaluation; retry"})
    return _ok(asdict(result))


@signals_router.get("/api/assurance/security-components")
def security_components(anchor_entity_id: str) -> JSONResponse:
    """Components of the anchor's active signal snapshot (exposure-filtered)."""
    from src.application.security_signals.signals_read import list_active_components  # noqa: PLC0415

    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return _ok({"components": [], "count": 0, "reason": "no co-located signals store"})
    components, withheld = list_active_components(anchor_entity_id, snapshot_store=snapshot_store, policy=pol)
    return _ok({"components": components, "count": len(components), "withheld": withheld})


@signals_router.get("/api/assurance/security-findings")
def security_findings(
    anchor_entity_id: str, purl: str | None = None, component_id: str | None = None,
) -> JSONResponse:
    """Vulnerability findings of the anchor's active snapshot, optionally scoped to one
    component by purl or component_id (the component-details view). Exposure-filtered."""
    from src.application.security_signals.signals_read import list_active_findings  # noqa: PLC0415

    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return _ok({"findings": [], "count": 0, "reason": "no co-located signals store"})
    findings, withheld = list_active_findings(
        anchor_entity_id, snapshot_store=snapshot_store, policy=pol, purl=purl, component_id=component_id)
    return _ok({"findings": findings, "count": len(findings), "withheld": withheld})


@signals_router.get("/api/assurance/security-stats")
def security_stats() -> JSONResponse:
    """Signal-snapshot aggregate counts (snapshots + active-snapshot components/findings)."""
    from src.application.security_signals.signals_read import signals_stats  # noqa: PLC0415

    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return _ok({"reason": "no co-located signals store"})
    return _ok(dict(signals_stats(snapshot_store=snapshot_store)))


class IngestSignalsBody(BaseModel):
    anchor_entity_id: str
    bom: dict[str, Any]
    vulnerabilities: list[dict[str, Any]] = []
    request_id: str = ""
    source: str = ""


@signals_router.post("/api/assurance/security-ingest")
def ingest_security_signals(body: IngestSignalsBody) -> JSONResponse:
    """Ingest a supplied CycloneDX BOM (+ optional OSV advisories) for one anchor,
    producing a new active signal snapshot. Same capability gate, same command, and
    same outcome projection as the MCP tool — only the status codes are HTTP's."""
    from src.infrastructure.assurance.signal_ingest import (  # noqa: PLC0415
        INGEST_STATUS_CODES,
        ingest_outcome_payload,
        ingest_supplied_bom,
    )

    ctx = get_assurance_context()
    capability = current_signal_mutation_capability(unlocked=ctx.is_available())
    if isinstance(capability, SignalMutationDenied):
        if capability.reason_code == "store_locked":
            return _locked_response()
        return JSONResponse(
            status_code=403,
            content={
                "error": "signal_mutation_denied",
                "reason_code": capability.reason_code,
                "message": capability.message,
            },
            headers={"Cache-Control": _NO_STORE},
        )
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:  # unreachable when the capability allowed the write
        return _locked_response()
    payload = ingest_outcome_payload(ingest_supplied_bom(
        body.anchor_entity_id,
        body.bom,
        records=body.vulnerabilities,
        snapshot_store=snapshot_store,
        request_id=body.request_id,
        source=body.source,
    ))
    return JSONResponse(
        status_code=INGEST_STATUS_CODES[str(payload["status"])],
        content=payload,
        headers={"Cache-Control": _NO_STORE},
    )


class RecordVexBody(BaseModel):
    anchor_entity_id: str
    canonical_component_id: str
    canonical_vulnerability_id: str
    vex_status: str
    justification: str = ""
    author: str
    source: str = ""


@signals_router.post("/api/assurance/vex", status_code=200)
def record_vex(body: RecordVexBody) -> JSONResponse:
    ctx = get_assurance_context()
    capability = current_signal_mutation_capability(unlocked=ctx.is_available())
    if isinstance(capability, SignalMutationDenied):
        if capability.reason_code == "store_locked":
            return _locked_response()
        return JSONResponse(
            status_code=403,
            content={
                "error": "signal_mutation_denied",
                "reason_code": capability.reason_code,
                "message": capability.message,
            },
            headers={"Cache-Control": _NO_STORE},
        )
    vex_store = ctx.vex_store
    if vex_store is None:  # unreachable when the capability allowed the write
        return _locked_response()
    result = run_write(lambda: record_vex_assessment(
        RecordVexRequest(
            anchor_entity_id=body.anchor_entity_id,
            canonical_component_id=body.canonical_component_id,
            canonical_vulnerability_id=body.canonical_vulnerability_id,
            vex_status=body.vex_status,
            justification=body.justification,
            author=body.author,
            source=body.source,
        ),
        store=vex_store,
    ))
    if isinstance(result, VexInvalid):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_vex_assessment",
                "errors": [{"field": e.field, "message": e.message} for e in result.errors],
            },
            headers={"Cache-Control": _NO_STORE},
        )
    return _ok({
        "assessment_id": result.assessment_id,
        "revision": result.revision,
        "created_at": result.created_at,
    })


@signals_router.get("/api/assurance/vex")
def list_vex(
    anchor_entity_id: str,
    canonical_component_id: str,
    canonical_vulnerability_id: str,
) -> JSONResponse:
    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    vex_store = ctx.vex_store
    if vex_store is None:
        return _ok({"revisions": [], "count": 0, "visibility_limited": pol.scope().visibility_limited})
    rows = vex_store.list_vex_revisions(
        anchor_entity_id=anchor_entity_id,
        canonical_component_id=canonical_component_id,
        canonical_vulnerability_id=canonical_vulnerability_id,
    )
    visible, _withheld = pol.filter_security_records(rows)
    return _ok({
        "revisions": visible,
        "count": len(visible),
        "visibility_limited": pol.scope().visibility_limited,
    })


class DeleteSnapshotBody(BaseModel):
    snapshot_id: str = ""
    anchor_entity_id: str = ""


@signals_router.post("/api/assurance/security-snapshot-delete")
def delete_security_snapshot(body: DeleteSnapshotBody) -> JSONResponse:
    """Delete one snapshot, or every snapshot for an anchor. Same capability gate
    and same body as the MCP tool — only the status codes are HTTP's.

    POST rather than DELETE: the request carries a body selecting EITHER a
    snapshot id OR an anchor, and DELETE with a semantic body is poorly supported
    across intermediaries.
    """
    from src.infrastructure.assurance.signal_deletion import (  # noqa: PLC0415
        DELETE_STATUS_CODES,
        delete_anchor_snapshots,
        delete_snapshot,
    )

    if bool(body.snapshot_id) == bool(body.anchor_entity_id):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_request",
                "message": "Pass exactly one of snapshot_id or anchor_entity_id.",
            },
            headers={"Cache-Control": _NO_STORE},
        )
    ctx = get_assurance_context()
    capability = current_signal_mutation_capability(unlocked=ctx.is_available())
    if isinstance(capability, SignalMutationDenied):
        if capability.reason_code == "store_locked":
            return _locked_response()
        return JSONResponse(
            status_code=403,
            content={
                "error": "signal_mutation_denied",
                "reason_code": capability.reason_code,
                "message": capability.message,
            },
            headers={"Cache-Control": _NO_STORE},
        )
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:  # unreachable when the capability allowed the write
        return _locked_response()
    payload = (
        delete_snapshot(body.snapshot_id, snapshot_store=snapshot_store)
        if body.snapshot_id
        else delete_anchor_snapshots(body.anchor_entity_id, snapshot_store=snapshot_store)
    )
    return JSONResponse(
        status_code=DELETE_STATUS_CODES[str(payload["status"])],
        content=payload,
        headers={"Cache-Control": _NO_STORE},
    )


@signals_router.get("/api/assurance/vulnerability-impact")
def vulnerability_impact(identifier: str) -> JSONResponse:
    """Every entity currently affected by one vulnerability, by any of its ids.

    The reverse of the anchor-keyed reads: resolves the identifier through the
    canonical identity that merges CVE/GHSA/PYSEC aliases, so the answer does not
    depend on which feed's id the caller happens to hold.
    """
    from src.infrastructure.assurance.signal_impact import (  # noqa: PLC0415
        IMPACT_STATUS_CODES,
        find_vulnerability_impact,
    )

    ctx, pol = _policy()
    if pol.check_locked():
        return _locked_response()
    snapshot_store = ctx.snapshot_store
    vex_store = ctx.vex_store
    if snapshot_store is None or vex_store is None:
        return _ok({"found": False, "affected": [], "reason": "no co-located signals store"})
    payload = find_vulnerability_impact(
        identifier, impact_store=snapshot_store, vex_store=vex_store, policy=pol)
    return JSONResponse(
        status_code=IMPACT_STATUS_CODES[str(payload["status"])],
        content=payload,
        headers={"Cache-Control": _NO_STORE},
    )


@signals_router.get("/api/assurance/signal-anchor-types")
def signal_anchor_types() -> JSONResponse:
    """Admissible ArchiMate anchor types for a signal snapshot.

    A single backend source of truth: clients consume this rather than redeclaring
    the list, so a GUI that offers ingest and an API that accepts it cannot drift
    apart. Un-gated — it is a static vocabulary, not store content.
    """
    from src.domain.assurance.security_signal_snapshot import ADMISSIBLE_ANCHOR_TYPES  # noqa: PLC0415

    return _ok({"anchor_types": list(ADMISSIBLE_ANCHOR_TYPES)})
