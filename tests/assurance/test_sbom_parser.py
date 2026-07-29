"""Tests for SBOM parsing (CycloneDX and SPDX formats)."""

from __future__ import annotations

from src.infrastructure.assurance._sbom_parser import parse_bom, parse_cyclonedx, parse_spdx


def _cdx_bom(components: list[dict] | None = None, serial: str = "urn:uuid:test-1") -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "serialNumber": serial,
        "version": 1,
        "components": components or [],
    }


def _cdx_component(name: str, purl: str = "", version: str = "1.0") -> dict:
    return {"name": name, "purl": purl, "version": version, "type": "library"}


def _spdx_bom(packages: list[dict] | None = None) -> dict:
    return {
        "spdxVersion": "SPDX-2.3",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "test-sbom",
        "packages": packages or [],
    }


def _spdx_package(name: str, version: str = "1.0", purl: str = "") -> dict:
    pkg: dict = {"name": name, "versionInfo": version, "SPDXID": f"SPDXRef-{name}"}
    if purl:
        pkg["externalRefs"] = [
            {"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": purl}
        ]
    return pkg


# ── CycloneDX ────────────────────────────────────────────────────────────────

class TestParseCycloneDX:
    def test_empty_bom(self) -> None:
        meta, comps = parse_cyclonedx(_cdx_bom())
        assert meta["bom_serial"] == "urn:uuid:test-1"
        assert comps == []

    def test_components_extracted(self) -> None:
        bom = _cdx_bom([
            _cdx_component("requests", "pkg:pypi/requests@2.31.0"),
            _cdx_component("flask", "pkg:pypi/flask@3.0.0"),
        ])
        meta, comps = parse_cyclonedx(bom)
        assert len(comps) == 2
        assert comps[0]["name"] == "requests"
        assert comps[0]["purl"] == "pkg:pypi/requests@2.31.0"
        assert comps[1]["component_type"] == "library"

    def test_metadata_component_included(self) -> None:
        bom = _cdx_bom()
        bom["metadata"] = {"component": {"name": "my-app", "type": "application", "version": "2.0"}}
        meta, comps = parse_cyclonedx(bom)
        assert len(comps) == 1
        assert comps[0]["name"] == "my-app"

    def test_missing_fields_default_empty(self) -> None:
        bom = {"bomFormat": "CycloneDX", "components": [{"name": "lib", "type": "library"}]}
        meta, comps = parse_cyclonedx(bom)
        assert comps[0]["purl"] == ""
        assert comps[0]["version"] == ""


# ── SPDX ─────────────────────────────────────────────────────────────────────

class TestParseSPDX:
    def test_empty_bom(self) -> None:
        meta, comps = parse_spdx(_spdx_bom())
        assert meta["bom_format"] == "spdx"
        assert comps == []

    def test_packages_extracted(self) -> None:
        bom = _spdx_bom([
            _spdx_package("requests", "2.31.0", "pkg:pypi/requests@2.31.0"),
            _spdx_package("flask", "3.0.0"),
        ])
        meta, comps = parse_spdx(bom)
        assert len(comps) == 2
        assert comps[0]["purl"] == "pkg:pypi/requests@2.31.0"
        assert comps[1]["purl"] == ""

    def test_version_from_name(self) -> None:
        pkg = {"name": "lib@1.2.3", "SPDXID": "SPDXRef-lib"}
        meta, comps = parse_spdx({"spdxVersion": "SPDX-2.3", "SPDXID": "X", "packages": [pkg]})
        assert comps[0]["version"] == "1.2.3"


# ── Auto-detect format ────────────────────────────────────────────────────────

class TestParseBom:
    def test_cyclonedx_detected(self) -> None:
        bom = _cdx_bom([_cdx_component("lib", "pkg:pypi/lib@1.0")])
        meta, comps = parse_bom(bom)
        assert meta["bom_format"] == "cyclonedx"
        assert len(comps) == 1

    def test_spdx_detected(self) -> None:
        bom = _spdx_bom([_spdx_package("lib")])
        meta, comps = parse_bom(bom)
        assert meta["bom_format"] == "spdx"
        assert len(comps) == 1

    def test_fallback_to_cyclonedx(self) -> None:
        bom = {"components": [{"name": "x"}]}
        meta, comps = parse_bom(bom)
        assert len(comps) == 1
