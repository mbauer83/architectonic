"""Assemble IngestBundle inputs from a parsed SBOM plus acquisition results.

Pure application logic: component identity (bom-ref first), directness from
the preserved dependency graph, per-finding applicability via the OSV range
semantics, severity selection with provenance, alias capture, and honest
diagnostics (unmatched components, failed fetches, invalid vectors,
not-applicable exclusions). Ecosystems come from the purl type; components
without a valid versioned purl are diagnostics, never silent drops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from packageurl import PackageURL

from src.application.security_signals.severity import select_severity
from src.domain.assurance.osv_ranges import evaluate_applicability
from src.domain.assurance.security_signal_snapshot import classify_directness


@dataclass(frozen=True)
class AcquisitionInputs:
    """What the OSV client learned, in transport-neutral form."""

    vulnerability_ids_by_component: Mapping[str, Sequence[str]]
    vulnerabilities_by_id: Mapping[str, Mapping[str, Any]]
    unmatched_components: Sequence[Mapping[str, str]] = ()
    failed_vulnerability_fetches: Sequence[Mapping[str, str]] = ()


@dataclass
class AssembledInputs:
    components: list[dict[str, object]] = field(default_factory=list)
    findings: list[dict[str, object]] = field(default_factory=list)
    queryable: list[dict[str, str]] = field(default_factory=list)  # component_id + purl
    diagnostics: dict[str, object] = field(default_factory=dict)


def component_identity(component: Mapping[str, object]) -> str:
    return str(component.get("bom_ref") or component.get("purl") or component.get("name") or "")


def _versioned_purl(component: Mapping[str, object]) -> PackageURL | None:
    raw = str(component.get("purl") or "")
    if not raw:
        return None
    try:
        purl = PackageURL.from_string(raw)
    except ValueError:
        return None
    return purl if purl.version else None


def prepare_components(
    meta: Mapping[str, object],
    parsed_components: Sequence[Mapping[str, object]],
) -> AssembledInputs:
    """Phase A: normalize components, classify directness, split queryable from
    unmatched. The caller then runs acquisition over `queryable`."""
    result = AssembledInputs()
    raw_edges = meta.get("dependencies")
    edges = [
        (str(entry["ref"]), str(target))
        for entry in (raw_edges if isinstance(raw_edges, list) else [])
        for target in entry.get("depends_on", [])
    ]
    root_ref = str(meta.get("root_bom_ref") or "")
    unmatched: list[dict[str, str]] = []
    for component in parsed_components:
        component_id = component_identity(component)
        if not component_id:
            unmatched.append({"component_id": "", "reason": "component has no identity"})
            continue
        bom_ref = str(component.get("bom_ref") or "")
        directness = (
            classify_directness(root_ref, bom_ref, edges)
            if root_ref and bom_ref else "unknown"
        )
        result.components.append({
            "component_id": component_id,
            "bom_ref": bom_ref,
            "purl": str(component.get("purl") or ""),
            "cpe": str(component.get("cpe") or ""),
            "name": str(component.get("name") or ""),
            "version": str(component.get("version") or ""),
            "component_type": str(component.get("component_type") or "library"),
            "group_name": str(component.get("group_name") or ""),
            "directness": directness,
        })
        if bool(component.get("is_root")):
            continue  # the root is the subject, never queried as a dependency
        purl = _versioned_purl(component)
        if purl is None:
            unmatched.append({
                "component_id": component_id,
                "reason": "no valid versioned purl — applicability unknown by construction",
            })
            continue
        result.queryable.append({"component_id": component_id, "purl": purl.to_string()})
    result.diagnostics["unmatched_components"] = unmatched
    return result


def attach_findings(result: AssembledInputs, acquisition: AcquisitionInputs) -> AssembledInputs:
    """Phase B: turn acquisition results into findings — one per
    (component, vulnerability record); not-applicable records are excluded and
    counted; unknown applicability stays visible on the finding."""
    purl_by_component = {
        str(c["component_id"]): str(c["purl"]) for c in result.components
    }
    not_applicable = 0
    invalid_vectors = 0
    for component_id, vuln_ids in acquisition.vulnerability_ids_by_component.items():
        raw_purl = purl_by_component.get(component_id, "")
        try:
            purl = PackageURL.from_string(raw_purl) if raw_purl else None
        except ValueError:
            purl = None
        for vuln_id in vuln_ids:
            record = acquisition.vulnerabilities_by_id.get(vuln_id)
            if record is None:
                continue  # already in failed_vulnerability_fetches
            affected = record.get("affected")
            applicability = evaluate_applicability(
                purl.type if purl else "",
                purl.version if purl and purl.version else "",
                affected if isinstance(affected, list) else [],
            )
            if applicability == "not_applicable":
                not_applicable += 1
                continue
            severity_entries = record.get("severity")
            selection = select_severity(
                severity_entries if isinstance(severity_entries, list) else [])
            invalid_vectors += selection.invalid_vector_count
            aliases = record.get("aliases")
            external_ids = [str(record.get("id") or vuln_id)] + [
                str(a) for a in (aliases if isinstance(aliases, list) else [])
            ]
            result.findings.append({
                "component_id": component_id,
                "external_ids": external_ids,
                "severity_band": selection.selected.severity_band if selection.selected else None,
                "cvss_score": selection.selected.cvss_score if selection.selected else None,
                "cvss_vector": selection.selected.cvss_vector if selection.selected else None,
                "severity_source": selection.selected.nomenclature if selection.selected else None,
                "applicability": applicability,
                "provenance": {"osv_id": vuln_id, "source": "osv"},
            })
    prior = result.diagnostics.get("unmatched_components")
    unmatched: list[Mapping[str, str]] = list(prior) if isinstance(prior, list) else []
    unmatched.extend(acquisition.unmatched_components)
    result.diagnostics.update({
        "unmatched_components": unmatched,
        "failed_vulnerability_fetches": list(acquisition.failed_vulnerability_fetches),
        "not_applicable_excluded": not_applicable,
        "invalid_severity_vectors": invalid_vectors,
    })
    return result
