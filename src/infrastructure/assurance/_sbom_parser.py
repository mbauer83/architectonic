"""SBOM parsing — CycloneDX JSON and SPDX JSON component extraction.

Returns a normalised list of component dicts regardless of input format.
Each component dict has: purl, cpe, name, version, component_type, group_name,
bom_ref, and is_root. Metadata preserves the BOM identity (serial/version),
the root component's ref, and the dependency graph as normalized edges —
directness classification needs all three, so the parser never drops them.
"""

from __future__ import annotations


def _normalise_cdx_component(comp: dict[str, object], *, is_root: bool = False) -> dict[str, object]:
    return {
        "purl": str(comp.get("purl") or ""),
        "cpe": str(comp.get("cpe") or ""),
        "name": str(comp.get("name") or ""),
        "version": str(comp.get("version") or ""),
        "component_type": str(comp.get("type") or "library"),
        "group_name": str(comp.get("group") or ""),
        "bom_ref": str(comp.get("bom-ref") or ""),
        "is_root": is_root,
    }


def _cdx_dependency_edges(data: dict[str, object]) -> list[dict[str, object]]:
    """CycloneDX `dependencies` as normalized {ref, depends_on} entries."""
    raw = data.get("dependencies")
    if not isinstance(raw, list):
        return []
    edges: list[dict[str, object]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref") or "")
        if not ref:
            continue
        depends_on = entry.get("dependsOn")
        targets = [str(t) for t in depends_on if isinstance(t, str)] if isinstance(depends_on, list) else []
        edges.append({"ref": ref, "depends_on": targets})
    return edges


def parse_cyclonedx(data: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Parse a CycloneDX JSON BOM.

    Returns (metadata, components) where metadata contains serialNumber and version.
    """
    meta: dict[str, object] = {
        "bom_serial": str(data.get("serialNumber") or ""),
        "bom_version": str(data.get("version") or "1"),
        "bom_format": "cyclonedx",
    }
    raw_components = data.get("components")
    if not isinstance(raw_components, list):
        raw_components = []
    components = [
        _normalise_cdx_component(c) for c in raw_components if isinstance(c, dict)
    ]
    # The metadata root component is preserved AND flagged — it is the subject
    # of the BOM, not a dependency, and directness classification starts at it.
    meta_block = data.get("metadata")
    if isinstance(meta_block, dict):
        root_comp = meta_block.get("component")
        if isinstance(root_comp, dict):
            normalised_root = _normalise_cdx_component(root_comp, is_root=True)
            components.insert(0, normalised_root)
            meta["root_bom_ref"] = normalised_root["bom_ref"]
    meta["dependencies"] = _cdx_dependency_edges(data)
    return meta, components


def _purl_from_spdx_package(pkg: dict[str, object]) -> str:
    """Best-effort PURL extraction from an SPDX package record."""
    ext_refs = pkg.get("externalRefs")
    if isinstance(ext_refs, list):
        for ref in ext_refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("referenceCategory") or "").upper() == "PACKAGE-MANAGER":
                locator = str(ref.get("referenceLocator") or "")
                if locator.startswith("pkg:"):
                    return locator
    return ""


def _parse_spdx_version(pkg: dict[str, object]) -> str:
    ver = pkg.get("versionInfo")
    if ver:
        return str(ver)
    name = str(pkg.get("name") or "")
    if "@" in name:
        return name.split("@", 1)[1]
    return ""


def parse_spdx(data: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Parse an SPDX JSON BOM.

    Returns (metadata, components).
    """
    meta: dict[str, object] = {
        "bom_serial": str(data.get("SPDXID") or ""),
        "bom_version": str(data.get("spdxVersion") or ""),
        "bom_format": "spdx",
    }
    raw_packages = data.get("packages")
    if not isinstance(raw_packages, list):
        raw_packages = []
    components: list[dict[str, object]] = []
    for pkg in raw_packages:
        if not isinstance(pkg, dict):
            continue
        name = str(pkg.get("name") or "")
        if not name:
            continue
        components.append({
            "purl": _purl_from_spdx_package(pkg),
            "cpe": "",
            "name": name,
            "version": _parse_spdx_version(pkg),
            "component_type": "library",
            "group_name": "",
            "bom_ref": str(pkg.get("SPDXID") or ""),
            "is_root": False,
        })
    meta["dependencies"] = _spdx_dependency_edges(data)
    return meta, components


def _spdx_dependency_edges(data: dict[str, object]) -> list[dict[str, object]]:
    """SPDX DEPENDS_ON relationships as normalized {ref, depends_on} entries."""
    raw = data.get("relationships")
    if not isinstance(raw, list):
        return []
    by_ref: dict[str, list[str]] = {}
    for rel in raw:
        if not isinstance(rel, dict):
            continue
        if str(rel.get("relationshipType") or "").upper() != "DEPENDS_ON":
            continue
        source = str(rel.get("spdxElementId") or "")
        target = str(rel.get("relatedSpdxElement") or "")
        if source and target:
            by_ref.setdefault(source, []).append(target)
    return [{"ref": ref, "depends_on": targets} for ref, targets in by_ref.items()]


def parse_bom(data: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Detect format and parse a BOM dict. Falls back to CycloneDX for unknown formats."""
    bom_format = str(data.get("bomFormat") or "").lower()
    spdx_version = str(data.get("spdxVersion") or "")
    if bom_format == "cyclonedx" or "components" in data:
        return parse_cyclonedx(data)
    if spdx_version.startswith("SPDX") or "packages" in data:
        return parse_spdx(data)
    # Last-resort: try CycloneDX
    return parse_cyclonedx(data)
