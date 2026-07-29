"""Turn caller-supplied OSV vulnerability records into AcquisitionInputs.

The offline counterpart of the OSV client: when the vulnerability records come
from the caller (an agent submitting a BOM plus advisories) rather than from a
live query, this module answers the one question the client's phase 1 answers —
*which component does each record concern* — by matching package identity
(purl type/namespace/name, version deliberately ignored). Version-range
applicability stays downstream in ``attach_findings``/``evaluate_applicability``,
so a supplied record is judged by exactly the same semantics as a fetched one.

Records that match no component are reported as diagnostics, never dropped.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from packageurl import PackageURL

from src.application.security_signals.bundle_assembly import AcquisitionInputs

PackageIdentity = tuple[str, str, str]  # purl type, namespace, name

# OSV ecosystem names → purl types, for records whose affected package carries an
# ecosystem/name pair instead of a purl.
_ECOSYSTEM_PURL_TYPES: Mapping[str, str] = {
    "pypi": "pypi",
    "npm": "npm",
    "go": "golang",
    "maven": "maven",
    "crates.io": "cargo",
    "nuget": "nuget",
    "rubygems": "gem",
    "packagist": "composer",
    "hex": "hex",
    "pub": "pub",
}


def _identity_of_purl(raw_purl: str) -> PackageIdentity | None:
    try:
        purl = PackageURL.from_string(raw_purl)
    except ValueError:
        return None
    return (purl.type.lower(), (purl.namespace or "").lower(), purl.name.lower())


def _identity_of_package(package: Mapping[str, Any]) -> PackageIdentity | None:
    """Identity of one OSV ``affected[].package``: its purl when present,
    otherwise its ecosystem/name pair mapped onto the purl type."""
    raw_purl = str(package.get("purl") or "")
    if raw_purl:
        return _identity_of_purl(raw_purl)
    # OSV ecosystems may carry a release suffix, e.g. "Debian:12" — the base name
    # is what identifies the packaging system.
    ecosystem = str(package.get("ecosystem") or "").split(":")[0].strip().lower()
    name = str(package.get("name") or "").strip()
    purl_type = _ECOSYSTEM_PURL_TYPES.get(ecosystem)
    if not purl_type or not name:
        return None
    namespace, _, bare = name.rpartition("/")
    return (purl_type, namespace.lower(), bare.lower())


def _record_identities(record: Mapping[str, Any]) -> set[PackageIdentity]:
    affected = record.get("affected")
    entries = affected if isinstance(affected, list) else []
    return {
        identity
        for entry in entries
        if isinstance(entry, Mapping)
        for package in [entry.get("package")]
        if isinstance(package, Mapping)
        for identity in [_identity_of_package(package)]
        if identity is not None
    }


def acquisition_from_records(
    queryable: Sequence[Mapping[str, str]],
    records: Sequence[Mapping[str, Any]],
) -> AcquisitionInputs:
    """Map supplied OSV records onto the queryable components by package identity.

    ``queryable`` is ``prepare_components(...).queryable`` — component_id + versioned
    purl. Returns the same shape the OSV client produces, so bundle assembly is
    identical for supplied and fetched data.
    """
    components_by_identity: dict[PackageIdentity, list[str]] = {}
    for component in queryable:
        identity = _identity_of_purl(str(component.get("purl") or ""))
        if identity is not None:
            components_by_identity.setdefault(identity, []).append(
                str(component["component_id"]))

    ids_by_component: dict[str, list[str]] = {}
    vulnerabilities_by_id: dict[str, dict[str, Any]] = {}
    unmatched_records: list[dict[str, str]] = []
    for record in records:
        record_id = str(record.get("id") or "")
        if not record_id:
            unmatched_records.append({"component_id": "", "reason": "record has no id"})
            continue
        matched = [
            component_id
            for identity in _record_identities(record)
            for component_id in components_by_identity.get(identity, ())
        ]
        if not matched:
            unmatched_records.append({
                "component_id": "",
                "reason": f"supplied record {record_id} matches no BOM component",
            })
            continue
        vulnerabilities_by_id[record_id] = dict(record)
        for component_id in matched:
            ids = ids_by_component.setdefault(component_id, [])
            if record_id not in ids:
                ids.append(record_id)

    return AcquisitionInputs(
        vulnerability_ids_by_component=ids_by_component,
        vulnerabilities_by_id=vulnerabilities_by_id,
        unmatched_components=unmatched_records,
    )
