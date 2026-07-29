"""The one boundary for the vulnerability → affected-entities query.

Mirrors ``signal_ingest`` and ``signal_deletion``: one projection shared by REST
and MCP so the two surfaces cannot drift, with the transports differing only in
how they express unavailability.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.application.security_signals.vulnerability_impact import (
    ImpactVexReads,
    VulnerabilityImpact,
    VulnerabilityImpactStore,
    find_affected_entities,
)

# HTTP status per outcome. An unknown identifier is 404: "this store has never
# heard of it" is materially different from "known, affects nothing", which is a
# 200 with an empty list.
IMPACT_STATUS_CODES: Mapping[str, int] = {"found": 200, "unknown_vulnerability": 404}


def impact_payload(impact: VulnerabilityImpact) -> dict[str, Any]:
    """Project the typed result onto the shared response body."""
    if not impact.found:
        return {
            "status": "unknown_vulnerability",
            "found": False,
            "notes": list(impact.notes),
        }
    return {
        "status": "found",
        "found": True,
        "canonical_id": impact.canonical_id,
        "aliases": list(impact.aliases),
        "affected_entity_count": impact.affected_entity_count,
        "open_entity_count": impact.open_entity_count,
        "max_severity_band": impact.max_severity_band,
        "max_cvss_score": impact.max_cvss_score,
        "withheld_count": impact.withheld_count,
        "affected": [
            {
                "anchor_entity_id": entity.anchor_entity_id,
                "snapshot_activated_at": entity.snapshot_activated_at,
                "open_component_count": entity.open_component_count,
                "components": [
                    {
                        "component_name": component.component_name,
                        "component_purl": component.component_purl,
                        "component_version": component.component_version,
                        "directness": component.directness,
                        "severity_band": component.severity_band,
                        "cvss_score": component.cvss_score,
                        "applicability": component.applicability,
                        "vex_status": component.vex_status,
                        "suppressed": component.suppressed,
                    }
                    for component in entity.components
                ],
            }
            for entity in impact.affected
        ],
        "notes": list(impact.notes),
    }


def find_vulnerability_impact(
    identifier: str,
    *,
    impact_store: VulnerabilityImpactStore,
    vex_store: ImpactVexReads,
    policy: Any,
) -> dict[str, Any]:
    """Resolve the identifier and project the impact — the whole act, defined once."""
    return impact_payload(find_affected_entities(
        identifier, impact_store=impact_store, vex_store=vex_store, policy=policy,
    ))
