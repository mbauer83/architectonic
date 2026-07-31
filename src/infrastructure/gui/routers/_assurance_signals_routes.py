"""Security-posture REST surface: metrics over the active signal snapshot and the
audited VEX mutation route. Reads are unlock-gated and exposure-filtered before aggregation;
VEX writes pass the signal-mutation capability gate (typed denial) and land data + audit in one
transaction.

Every route here is anchored to one architecture artifact, so the anchor is a path segment and no
body repeats it. ``Cache-Control: no-store`` is no longer written by hand: the manifest declares it
for the whole ``/api/assurance`` prefix and the cache-directive middleware applies it, which is what
makes it impossible for the next route added here to be the one that forgets.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

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
from src.infrastructure.gui.contracts.assurance_signals import (
    SecurityComponentListResponse,
    SecurityComponentResponse,
    SecurityFindingListResponse,
    SecurityMetricsResponse,
    SecuritySignalStatsResponse,
    SignalAnchorTypeListResponse,
    SignalIngestResponse,
    VexAssessmentListResponse,
    VexAssessmentResponse,
    VulnerabilityImpactResponse,
)
from src.infrastructure.gui.contracts.errors import (
    ApiError,
    DenialDetails,
    ErrorCode,
    FieldError,
    ValidationErrorDetails,
)
from src.infrastructure.gui.routers._assurance_http import not_found as _not_found
from src.infrastructure.gui.routers._assurance_http import store_locked as _store_locked
from src.infrastructure.gui.routers._openapi import TAG_ASSURANCE
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context

signals_router = APIRouter(tags=[TAG_ASSURANCE])

_NO_SIGNALS_STORE = "no co-located signals store"

# Every route here declares ``response_model_exclude_unset``. The DTOs enumerate which keys an
# outcome *may* carry — the outcome itself is named by ``status`` or ``availability`` — and the
# response is exactly the keys the projection produced. Not ``exclude_none``: a key the projection
# emits as null is part of its answer, and the REST and MCP surfaces are required to return the
# same body for the same command.


def _policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    # Defined locally (not imported) so the context lookup is patched at this module.
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


def _readable_context() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    """The context for a read, or the locked refusal — one place, so no read forgets the gate."""
    ctx, policy = _policy()
    if policy.check_locked():
        raise _store_locked()
    return ctx, policy


def _mutating_context() -> AssuranceContext:
    """The context for a signal write, having passed the capability gate.

    A denial is an error rather than a 403 body a caller has to recognise: ``reason_code`` is what
    a client branches on, and ``store_locked`` is a different remedy from a withheld capability.
    """
    ctx = get_assurance_context()
    capability = current_signal_mutation_capability(unlocked=ctx.is_available())
    if isinstance(capability, SignalMutationDenied):
        if capability.reason_code == "store_locked":
            raise _store_locked()
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "signal_mutation_denied",
            capability.message,
            DenialDetails(reason_code=capability.reason_code),
        )
    if ctx.snapshot_store is None:  # unreachable when the capability allowed the write
        raise _store_locked()
    return ctx


@signals_router.get("/api/assurance/arch-artifacts/{arch_artifact_id}/security-metrics",
    summary="Security posture for one anchor", response_model=SecurityMetricsResponse,
    response_model_exclude_unset=True)
def security_metrics(arch_artifact_id: str) -> dict[str, Any]:
    ctx, pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    vex_store = ctx.vex_store
    if snapshot_store is None or vex_store is None:
        return {
            "availability": "unavailable",
            "reason": "metrics require the SQLCipher store with co-located signals",
        }
    if not isinstance(ctx.store, AvailabilityState):
        metrics = compute_security_metrics(
            arch_artifact_id, snapshot_store=snapshot_store, vex_store=vex_store, policy=pol,
        )
        return asdict(metrics)
    # Snapshot pinning: the whole read batch happens under one token; any
    # activation / lock cycle / ceiling / VEX change mid-evaluation yields
    # unavailable/retry — never values mixing two snapshots.
    result, _token = evaluate_pinned(
        arch_artifact_id,
        availability=ctx.store,
        snapshot_store=snapshot_store,
        vex_store=vex_store,
        exposure_ceiling=ctx.max_classification,
        evaluate=lambda: compute_security_metrics(
            arch_artifact_id, snapshot_store=snapshot_store, vex_store=vex_store, policy=pol,
        ),
    )
    if result is None:
        return {"availability": "unavailable", "reason": "snapshot changed mid-evaluation; retry"}
    return asdict(result)


@signals_router.get("/api/assurance/arch-artifacts/{arch_artifact_id}/security-components",
    summary="Components of an anchor's active snapshot",
    response_model=SecurityComponentListResponse,
    response_model_exclude_unset=True)
def security_components(arch_artifact_id: str) -> dict[str, Any]:
    """Components of the anchor's active signal snapshot (exposure-filtered)."""
    from src.application.security_signals.signals_read import list_active_components  # noqa: PLC0415

    ctx, pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return {"components": [], "count": 0, "reason": _NO_SIGNALS_STORE}
    components, withheld = list_active_components(arch_artifact_id, snapshot_store=snapshot_store, policy=pol)
    return {"components": components, "count": len(components), "withheld": withheld}


@signals_router.get("/api/assurance/security-components/{component_id}",
    summary="One security component by its internal id", response_model=SecurityComponentResponse)
def security_component(component_id: str) -> dict[str, Any]:
    """One component, addressed by the ``SCM@…`` id this system minted for it.

    Not by its PURL. A PURL identifies a *package* in a vocabulary another standard owns, its
    grammar carries `/`, `?` and `#` deliberately, and the same package arrives under different
    references from different feeds — so it filters the collection
    (``…/security-components?purl=``) and it is stored on the row, but it does not address the
    resource. See ADR *Resource Addressing: Identity in the Path, Filters in the Query*.

    Above-ceiling components answer 404, identically to absent ones: a distinguishable refusal
    would disclose that the component exists.
    """
    ctx, pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        raise _not_found(_NO_SIGNALS_STORE)
    row = snapshot_store.get_component(component_id)
    if row is None:
        raise _not_found(f"no security component {component_id!r}")
    visible, _withheld = pol.filter_security_records([row])
    if not visible:
        raise _not_found(f"no security component {component_id!r}")
    return {"component": visible[0]}


@signals_router.get("/api/assurance/arch-artifacts/{arch_artifact_id}/security-findings",
    summary="Findings of an anchor's active snapshot", response_model=SecurityFindingListResponse,
    response_model_exclude_unset=True)
def security_findings(
    arch_artifact_id: str, purl: str | None = None, component_id: str | None = None,
) -> dict[str, Any]:
    """Vulnerability findings of the anchor's active snapshot, optionally scoped to one
    component by purl or component_id (the component-details view). Exposure-filtered."""
    from src.application.security_signals.signals_read import list_active_findings  # noqa: PLC0415

    ctx, pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return {"findings": [], "count": 0, "reason": _NO_SIGNALS_STORE}
    findings, withheld = list_active_findings(
        arch_artifact_id, snapshot_store=snapshot_store, policy=pol, purl=purl, component_id=component_id)
    return {"findings": findings, "count": len(findings), "withheld": withheld}


@signals_router.get("/api/assurance/security-stats", summary="Signal-snapshot aggregates",
    response_model=SecuritySignalStatsResponse,
    response_model_exclude_unset=True)
def security_stats() -> dict[str, Any]:
    """Signal-snapshot aggregate counts (snapshots + active-snapshot components/findings)."""
    from src.application.security_signals.signals_read import signals_stats  # noqa: PLC0415

    ctx, _pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    if snapshot_store is None:
        return {"reason": _NO_SIGNALS_STORE}
    return dict(signals_stats(snapshot_store=snapshot_store))


class _ClosedBody(BaseModel):
    """A request body that rejects what it does not declare — including a repeated path identity."""

    model_config = ConfigDict(extra="forbid")


class IngestSignalsBody(_ClosedBody):
    bom: dict[str, Any]
    vulnerabilities: list[dict[str, Any]] = []
    request_id: str = ""
    source: str = ""


@signals_router.post("/api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots",
    summary="Ingest a BOM as a new snapshot", response_model=SignalIngestResponse,
    response_model_exclude_unset=True)
def ingest_security_signals(arch_artifact_id: str, body: IngestSignalsBody) -> dict[str, Any]:
    """Ingest a supplied CycloneDX BOM (+ optional OSV advisories) for one anchor,
    producing a new active signal snapshot. Same capability gate, same command, and
    same outcome projection as the MCP tool.

    The anchor is the path; ``status`` in the body reports which outcome occurred. The status code
    stays the projection's own — a replay is not a fresh activation, and the two are distinguished
    by both.
    """
    from src.infrastructure.assurance.signal_ingest import (  # noqa: PLC0415
        ingest_outcome_payload,
        ingest_supplied_bom,
    )

    ctx = _mutating_context()
    assert ctx.snapshot_store is not None  # noqa: S101 — established by the capability gate
    payload = dict(ingest_outcome_payload(ingest_supplied_bom(
        arch_artifact_id,
        body.bom,
        records=body.vulnerabilities,
        snapshot_store=ctx.snapshot_store,
        request_id=body.request_id,
        source=body.source,
    )))
    _reject_failed_ingest(payload)
    return payload


def _reject_failed_ingest(payload: dict[str, Any]) -> None:
    """Turn a non-success ingest outcome into the shared envelope, keeping its status.

    The projection already decides which outcomes are failures and with what status; that decision
    stays where it is, and only the *shape* changes — an unsuccessful ingest is an error body, not a
    success body carrying a status word a caller has to know to read.
    """
    from src.infrastructure.assurance.signal_ingest import INGEST_STATUS_CODES  # noqa: PLC0415

    outcome = str(payload.get("status"))
    status_code = INGEST_STATUS_CODES[outcome]
    if status_code < 400:
        return
    if outcome == "invalid":
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "the submitted BOM was rejected",
            ValidationErrorDetails(
                field_errors=[
                    FieldError(field=str(e["field"]), message=str(e["message"]))
                    for e in payload.get("errors", [])
                ]
            ),
        )
    message = str(payload.get("message") or payload.get("reason") or f"ingest {outcome}")
    code: ErrorCode = "conflict" if status_code == status.HTTP_409_CONFLICT else "internal_error"
    raise ApiError(status_code, code, message)


class RecordVexBody(_ClosedBody):
    canonical_component_id: str
    canonical_vulnerability_id: str
    vex_status: str
    justification: str = ""
    author: str
    source: str = ""


@signals_router.post("/api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments",
    summary="Record a VEX assessment", response_model=VexAssessmentResponse)
def record_vex(arch_artifact_id: str, body: RecordVexBody) -> dict[str, Any]:
    ctx = _mutating_context()
    vex_store = ctx.vex_store
    if vex_store is None:  # unreachable when the capability allowed the write
        raise _store_locked()
    result = run_write(lambda: record_vex_assessment(
        RecordVexRequest(
            anchor_entity_id=arch_artifact_id,
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
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_vex_assessment",
            "the assessment was rejected",
            ValidationErrorDetails(
                field_errors=[FieldError(field=e.field, message=e.message) for e in result.errors]
            ),
        )
    return {
        "assessment_id": result.assessment_id,
        "revision": result.revision,
        "created_at": result.created_at,
    }


@signals_router.get("/api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments",
    summary="VEX revisions for one component/vulnerability pair",
    response_model=VexAssessmentListResponse,
    response_model_exclude_unset=True)
def list_vex(
    arch_artifact_id: str,
    canonical_component_id: str,
    canonical_vulnerability_id: str,
) -> dict[str, Any]:
    ctx, pol = _readable_context()
    vex_store = ctx.vex_store
    if vex_store is None:
        return {"revisions": [], "count": 0, "visibility_limited": pol.scope().visibility_limited}
    rows = vex_store.list_vex_revisions(
        anchor_entity_id=arch_artifact_id,
        canonical_component_id=canonical_component_id,
        canonical_vulnerability_id=canonical_vulnerability_id,
    )
    visible, _withheld = pol.filter_security_records(rows)
    return {
        "revisions": visible,
        "count": len(visible),
        "visibility_limited": pol.scope().visibility_limited,
    }


@signals_router.get("/api/assurance/vulnerabilities/{identifier}/impact",
    summary="Entities affected by one vulnerability", response_model=VulnerabilityImpactResponse,
    response_model_exclude_unset=True)
def vulnerability_impact(identifier: str) -> dict[str, Any]:
    """Every entity currently affected by one vulnerability, by any of its ids.

    The reverse of the anchor-keyed reads: resolves the identifier through the
    canonical identity that merges CVE/GHSA/PYSEC aliases, so the answer does not
    depend on which feed's id the caller happens to hold.
    """
    from src.infrastructure.assurance.signal_impact import find_vulnerability_impact  # noqa: PLC0415

    ctx, pol = _readable_context()
    snapshot_store = ctx.snapshot_store
    vex_store = ctx.vex_store
    if snapshot_store is None or vex_store is None:
        return {"found": False, "affected": [], "reason": _NO_SIGNALS_STORE}
    payload = dict(find_vulnerability_impact(
        identifier, impact_store=snapshot_store, vex_store=vex_store, policy=pol))
    if not payload.get("found"):
        notes = "; ".join(str(note) for note in payload.get("notes", []))
        raise _not_found(notes or f"no active snapshot mentions {identifier!r}")
    return payload


@signals_router.get("/api/assurance/signal-anchor-types", summary="Admissible anchor types",
    response_model=SignalAnchorTypeListResponse)
def signal_anchor_types() -> dict[str, Any]:
    """Admissible ArchiMate anchor types for a signal snapshot.

    A single backend source of truth: clients consume this rather than redeclaring
    the list, so a GUI that offers ingest and an API that accepts it cannot drift
    apart. Un-gated — it is a static vocabulary, not store content.
    """
    from src.domain.assurance.security_signal_snapshot import ADMISSIBLE_ANCHOR_TYPES  # noqa: PLC0415

    return {"anchor_types": list(ADMISSIBLE_ANCHOR_TYPES)}
