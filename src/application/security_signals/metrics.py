"""Security posture metrics — one pure use case over (active snapshot snapshot,
visible VEX revisions, exposure policy).

Filter-before-aggregate: the exposure policy is applied to components,
findings, and VEX revisions BEFORE any count, maximum, band, or classification
is computed. Classification is the maximum TLP of VISIBLE contributors; no
total is ever computed from hidden rows; all-hidden yields an empty
``visibility_limited`` projection — never "zero vulnerabilities". Visibility is
evaluated before suppression: a VEX revision the caller cannot see never
suppresses a finding the caller can see.

Vocabulary is unit-explicit: severity-band counts and per-directness counts
are COMPONENT FINDINGS; ``distinct_open_vulnerabilities`` counts canonical
vulnerability identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.domain.assurance.vex_assessment import SUPPRESSING_VEX_STATUSES

ContentState = Literal["complete", "visibility_limited", "no_active_snapshot", "no_findings"]

_TLP_ORDER = ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED")
_BAND_ORDER = ("none", "low", "medium", "high", "critical")


class MetricsRunReads(Protocol):
    def get_active_snapshot(self, anchor_entity_id: str) -> Mapping[str, Any] | None: ...

    def list_snapshot_components(self, snapshot_id: str) -> list[dict[str, Any]]: ...

    def list_snapshot_findings(self, snapshot_id: str) -> list[dict[str, Any]]: ...


class MetricsVexReads(Protocol):
    def list_anchor_assessments(self, anchor_entity_id: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class SecurityMetrics:
    availability: Literal["available", "unavailable"]
    content_state: ContentState
    visibility_limited: bool
    basis_snapshot_id: str | None
    basis_activated_at: str | None
    computed_classification: str | None
    component_count: int
    finding_total: int
    open_component_findings: dict[str, int]  # by directness class
    distinct_open_vulnerabilities: int
    severity_band_counts: dict[str, int]  # open component findings per band
    max_cvss_score: float | None
    max_severity_band: str | None
    applicability_unknown_count: int
    unknown_severity_finding_count: int
    suppressed_finding_count: int


def _max_tlp(rows: Sequence[Mapping[str, Any]]) -> str | None:
    levels = [
        _TLP_ORDER.index(str(row.get("tlp", "TLP:AMBER")))
        for row in rows
        if str(row.get("tlp", "TLP:AMBER")) in _TLP_ORDER
    ]
    return _TLP_ORDER[max(levels)] if levels else None


def _current_visible_vex(visible_revisions: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    current: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in visible_revisions:
        key = (str(row["canonical_component_id"]), str(row["canonical_vulnerability_id"]))
        held = current.get(key)
        if held is None or int(row["revision"]) > int(held["revision"]):
            current[key] = row
    return current


def compute_security_metrics(
    anchor_entity_id: str,
    *,
    snapshot_store: MetricsRunReads,
    vex_store: MetricsVexReads,
    policy: AssuranceExposurePolicy,
) -> SecurityMetrics:
    empty: dict[str, int] = {}
    snapshot = snapshot_store.get_active_snapshot(anchor_entity_id)
    if snapshot is None:
        return SecurityMetrics(
            availability="available", content_state="no_active_snapshot",
            visibility_limited=False,
            basis_snapshot_id=None, basis_activated_at=None, computed_classification=None,
            component_count=0, finding_total=0, open_component_findings=empty,
            distinct_open_vulnerabilities=0, severity_band_counts=empty,
            max_cvss_score=None, max_severity_band=None,
            applicability_unknown_count=0, unknown_severity_finding_count=0,
            suppressed_finding_count=0,
        )
    snapshot_id = str(snapshot["snapshot_id"])

    # Filter BEFORE any aggregation.
    visible_components, hidden_components = policy.filter_security_records(
        snapshot_store.list_snapshot_components(snapshot_id))
    visible_findings, hidden_findings = policy.filter_security_records(
        snapshot_store.list_snapshot_findings(snapshot_id))
    visible_vex, _hidden_vex = policy.filter_security_records(
        vex_store.list_anchor_assessments(anchor_entity_id))

    visible_component_ids = {str(c["component_id"]) for c in visible_components}
    component_by_id = {str(c["component_id"]): c for c in visible_components}
    # A finding is only visible when its component is also visible.
    visible_findings = [
        f for f in visible_findings if str(f["component_id"]) in visible_component_ids
    ]

    current_vex = _current_visible_vex(visible_vex)

    open_findings: list[Mapping[str, Any]] = []
    suppressed = 0
    for finding in visible_findings:
        component = component_by_id[str(finding["component_id"])]
        component_key = str(component.get("purl") or component.get("source_component_id") or "")
        vex_row = current_vex.get((component_key, str(finding["canonical_vulnerability_id"])))
        if vex_row is not None and str(vex_row["vex_status"]) in SUPPRESSING_VEX_STATUSES:
            suppressed += 1
            continue
        open_findings.append(finding)

    by_directness: dict[str, int] = {}
    for finding in open_findings:
        component = component_by_id[str(finding["component_id"])]
        directness = str(component.get("directness") or "unknown")
        by_directness[directness] = by_directness.get(directness, 0) + 1

    band_counts: dict[str, int] = {}
    unknown_severity = 0
    scores: list[float] = []
    for finding in open_findings:
        band = str(finding.get("severity_band") or "").lower()
        if band in _BAND_ORDER:
            band_counts[band] = band_counts.get(band, 0) + 1
        else:
            unknown_severity += 1
        score = finding.get("cvss_score")
        if isinstance(score, (int, float)):
            scores.append(float(score))

    known_bands = [b for b in band_counts if band_counts[b] > 0]
    max_band = max(known_bands, key=_BAND_ORDER.index) if known_bands else None
    applicability_unknown = sum(
        1 for f in open_findings if str(f.get("applicability") or "") == "unknown"
    )
    classification = _max_tlp([snapshot, *visible_components, *visible_findings])

    # The flag means content was ACTUALLY withheld from THIS response — not merely
    # that the session ceiling sits below the top level. A read that returns everything
    # in the store must not carry a "some info hidden" caveat.
    anything_hidden = bool(hidden_components or hidden_findings)
    if not visible_components and (hidden_components or hidden_findings):
        content_state: ContentState = "visibility_limited"
    elif not open_findings and not visible_findings:
        content_state = "visibility_limited" if anything_hidden else "no_findings"
    else:
        content_state = "visibility_limited" if anything_hidden else "complete"

    return SecurityMetrics(
        availability="available",
        content_state=content_state,
        visibility_limited=anything_hidden,
        basis_snapshot_id=snapshot_id,
        basis_activated_at=str(snapshot.get("activated_at") or ""),
        computed_classification=classification,
        component_count=len(visible_components),
        finding_total=len(visible_findings),
        open_component_findings=by_directness,
        distinct_open_vulnerabilities=len({
            str(f["canonical_vulnerability_id"]) for f in open_findings
        }),
        severity_band_counts=band_counts,
        max_cvss_score=max(scores) if scores else None,
        max_severity_band=max_band,
        applicability_unknown_count=applicability_unknown,
        unknown_severity_finding_count=unknown_severity,
        suppressed_finding_count=suppressed,
    )
