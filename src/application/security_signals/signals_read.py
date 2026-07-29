"""Read the ACTIVE signal snapshot's itemized signal data, exposure-filtered.

The single application read surface behind the signal LIST tools (MCP + REST):
components of the active snapshot, and vulnerability findings (optionally scoped to one
component / purl) — always filtered by the exposure policy BEFORE returning, with a
finding only visible when its component is also visible (the same consistency rule
``compute_security_metrics`` applies). Aggregate counts read the snapshot model directly
(operational view; no per-record exposure filter, mirroring the old store stats).
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from src.application.assurance_exposure import AssuranceExposurePolicy


class SnapshotReadStore(Protocol):
    """The signal-snapshot read slice the signal LIST surface needs (segregated port)."""

    def get_active_snapshot(self, anchor_entity_id: str) -> Mapping[str, Any] | None: ...
    def list_snapshot_components(self, snapshot_id: str) -> list[dict[str, Any]]: ...
    def list_snapshot_findings(self, snapshot_id: str) -> list[dict[str, Any]]: ...
    def list_snapshots(self, *, anchor_entity_id: str | None = None) -> list[dict[str, Any]]: ...


def _active_snapshot_id(anchor_entity_id: str, snapshot_store: SnapshotReadStore) -> str | None:
    snapshot = snapshot_store.get_active_snapshot(anchor_entity_id)
    return str(snapshot["snapshot_id"]) if snapshot is not None else None


def list_active_components(
    anchor_entity_id: str, *, snapshot_store: SnapshotReadStore, policy: AssuranceExposurePolicy,
) -> tuple[list[dict[str, Any]], int]:
    """Visible components of the anchor's active snapshot + the withheld count."""
    snapshot_id = _active_snapshot_id(anchor_entity_id, snapshot_store)
    if snapshot_id is None:
        return [], 0
    visible, withheld = policy.filter_security_records(snapshot_store.list_snapshot_components(snapshot_id))
    return visible, withheld


def list_active_findings(
    anchor_entity_id: str,
    *,
    snapshot_store: SnapshotReadStore,
    policy: AssuranceExposurePolicy,
    purl: str | None = None,
    component_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Visible findings of the anchor's active snapshot (optionally scoped to one component
    by ``component_id`` or ``purl``), each enriched with its component name/purl. A
    finding is withheld when its component is hidden, so the two stay consistent."""
    snapshot_id = _active_snapshot_id(anchor_entity_id, snapshot_store)
    if snapshot_id is None:
        return [], 0
    visible_components, _ = policy.filter_security_records(snapshot_store.list_snapshot_components(snapshot_id))
    component_by_id = {str(c["component_id"]): c for c in visible_components}
    visible_findings, withheld = policy.filter_security_records(snapshot_store.list_snapshot_findings(snapshot_id))
    out: list[dict[str, Any]] = []
    for finding in visible_findings:
        cid = str(finding["component_id"])
        component = component_by_id.get(cid)
        if component is None:
            withheld += 1  # its component is hidden → the finding is hidden with it
            continue
        if component_id is not None and cid != component_id:
            continue
        if purl is not None and str(component.get("purl") or "") != purl:
            continue
        out.append({
            **dict(finding),
            "assessed_entity_id": anchor_entity_id,
            "component_name": component.get("name"),
            "component_purl": component.get("purl"),
            "component_directness": component.get("directness"),
        })
    return out, withheld


def _active_assessed_entity_ids(snapshot_store: SnapshotReadStore) -> list[str]:
    """The architecture entities with an active security-signal snapshot (the assessed
    entities), sorted for deterministic output."""
    return sorted(
        {str(r["anchor_entity_id"]) for r in snapshot_store.list_snapshots() if str(r["status"]) == "active"}
    )


def list_all_active_findings(
    *,
    snapshot_store: SnapshotReadStore,
    policy: AssuranceExposurePolicy,
    purl: str | None = None,
    component_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Visible findings across the active snapshots of ALL assessed entities (each finding
    tagged with its ``assessed_entity_id``). The cross-entity view behind the no-anchor
    ``assurance_list_vulnerabilities`` call. Exposure-filtered per entity, same as the
    single-entity path."""
    out: list[dict[str, Any]] = []
    withheld = 0
    for entity_id in _active_assessed_entity_ids(snapshot_store):
        findings, w = list_active_findings(
            entity_id, snapshot_store=snapshot_store, policy=policy, purl=purl, component_id=component_id,
        )
        out.extend(findings)
        withheld += w
    return out, withheld


def signals_stats(*, snapshot_store: SnapshotReadStore) -> dict[str, Any]:
    """Operational aggregate over the signal-snapshot model (privileged, unfiltered — the
    tool is unlock-gated). Counts snapshots and the SBOM components / findings of the active
    snapshots, and enumerates the ASSESSED ENTITIES (the architecture entities that have an
    active security-signal snapshot) so callers need no out-of-band lookup to learn which
    entities carry signals. ``bom_component_count`` names the SBOM package count explicitly, to
    keep it distinct from the architecture *component* the snapshot is attached to."""
    snapshots = snapshot_store.list_snapshots()
    active = [r for r in snapshots if str(r["status"]) == "active"]
    assessed_entities: list[dict[str, Any]] = []
    components = 0
    findings = 0
    for snapshot in active:
        snapshot_id = str(snapshot["snapshot_id"])
        bom_component_count = len(snapshot_store.list_snapshot_components(snapshot_id))
        finding_count = len(snapshot_store.list_snapshot_findings(snapshot_id))
        components += bom_component_count
        findings += finding_count
        assessed_entities.append({
            "entity_id": str(snapshot["anchor_entity_id"]),
            "snapshot_id": snapshot_id,
            "bom_component_count": bom_component_count,
            "finding_count": finding_count,
        })
    assessed_entities.sort(key=lambda r: r["entity_id"])
    return {
        "total_snapshots": len(snapshots),
        "active_snapshots": len(active),
        "assessed_entity_count": len({r["entity_id"] for r in assessed_entities}),
        "assessed_entities": assessed_entities,
        "active_snapshot_bom_components": components,
        "active_snapshot_findings": findings,
    }
