"""Bundle assembly: component identity + directness from the preserved graph,
root never queried, versionless components → explicit diagnostics, findings
with applicability/severity/aliases, not-applicable exclusion counted."""

from __future__ import annotations

from src.application.security_signals.bundle_assembly import (
    AcquisitionInputs,
    attach_findings,
    prepare_components,
)

META = {
    "root_bom_ref": "root-app",
    "dependencies": [
        {"ref": "root-app", "depends_on": ["ref-a"]},
        {"ref": "ref-a", "depends_on": ["ref-b"]},
    ],
}
COMPONENTS = [
    {"bom_ref": "root-app", "name": "arch-repo", "is_root": True, "purl": ""},
    {"bom_ref": "ref-a", "name": "a", "version": "1.0.0", "purl": "pkg:pypi/a@1.0.0"},
    {"bom_ref": "ref-b", "name": "b", "version": "2.0.0", "purl": "pkg:pypi/b@2.0.0"},
    {"bom_ref": "ref-c", "name": "c", "version": "", "purl": ""},  # versionless
]

OSV_RECORD = {
    "id": "OSV-1",
    "aliases": ["CVE-2024-1", "GHSA-x"],
    "affected": [{"ranges": [{"type": "ECOSYSTEM", "events": [
        {"introduced": "0"}, {"fixed": "1.5.0"},
    ]}]}],
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N"}],
}
NOT_APPLICABLE_RECORD = {
    "id": "OSV-2",
    "affected": [{"ranges": [{"type": "ECOSYSTEM", "events": [
        {"introduced": "5.0.0"}, {"fixed": "6.0.0"},
    ]}]}],
}


class TestPrepare:
    def test_directness_and_queryable_split(self) -> None:
        result = prepare_components(META, COMPONENTS)
        by_id = {c["component_id"]: c for c in result.components}
        assert by_id["ref-a"]["directness"] == "direct"
        assert by_id["ref-b"]["directness"] == "transitive"
        assert by_id["root-app"]["directness"] == "unknown"
        assert [q["component_id"] for q in result.queryable] == ["ref-a", "ref-b"]

    def test_root_is_never_queried_and_versionless_is_diagnosed(self) -> None:
        result = prepare_components(META, COMPONENTS)
        queried = {q["component_id"] for q in result.queryable}
        assert "root-app" not in queried
        unmatched = result.diagnostics["unmatched_components"]
        assert [u["component_id"] for u in unmatched] == ["ref-c"]  # type: ignore[index]


class TestAttachFindings:
    def test_applicable_finding_carries_severity_aliases_and_provenance(self) -> None:
        result = prepare_components(META, COMPONENTS)
        attach_findings(result, AcquisitionInputs(
            vulnerability_ids_by_component={"ref-a": ["OSV-1"]},
            vulnerabilities_by_id={"OSV-1": OSV_RECORD},
        ))
        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding["component_id"] == "ref-a"
        assert finding["external_ids"] == ["OSV-1", "CVE-2024-1", "GHSA-x"]
        assert finding["severity_band"] == "medium"
        assert finding["cvss_score"] == 5.4
        assert finding["applicability"] == "applicable"
        assert finding["provenance"] == {"osv_id": "OSV-1", "source": "osv"}

    def test_not_applicable_records_are_excluded_and_counted(self) -> None:
        result = prepare_components(META, COMPONENTS)
        attach_findings(result, AcquisitionInputs(
            vulnerability_ids_by_component={"ref-a": ["OSV-2"]},
            vulnerabilities_by_id={"OSV-2": NOT_APPLICABLE_RECORD},
        ))
        assert result.findings == []
        assert result.diagnostics["not_applicable_excluded"] == 1

    def test_failed_fetches_flow_into_diagnostics(self) -> None:
        result = prepare_components(META, COMPONENTS)
        attach_findings(result, AcquisitionInputs(
            vulnerability_ids_by_component={"ref-a": ["OSV-9"]},
            vulnerabilities_by_id={},
            failed_vulnerability_fetches=[{"vulnerability_id": "OSV-9", "reason": "x"}],
        ))
        assert result.findings == []
        assert result.diagnostics["failed_vulnerability_fetches"] == [
            {"vulnerability_id": "OSV-9", "reason": "x"},
        ]
