"""The shared ingest submission boundary: a CycloneDX document plus an injected
acquisition strategy becomes one complete, digest-stable bundle — directness from
the dependency graph, BOM identity preserved, request ids generated when absent."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.application.security_signals.bundle_assembly import AcquisitionInputs
from src.application.security_signals.supplied_acquisition import acquisition_from_records
from src.infrastructure.assurance.signal_ingest import assemble_bundle

_BOM: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "serialNumber": "urn:uuid:abc",
    "version": 3,
    "metadata": {"component": {"bom-ref": "root", "name": "app", "version": "1.0"}},
    "components": [
        {"bom-ref": "direct", "name": "requests", "version": "2.31.0",
         "purl": "pkg:pypi/requests@2.31.0"},
        {"bom-ref": "indirect", "name": "urllib3", "version": "1.26.0",
         "purl": "pkg:pypi/urllib3@1.26.0"},
    ],
    "dependencies": [
        {"ref": "root", "dependsOn": ["direct"]},
        {"ref": "direct", "dependsOn": ["indirect"]},
    ],
}


def _no_findings(_queryable: Sequence[Mapping[str, str]]) -> AcquisitionInputs:
    return AcquisitionInputs(vulnerability_ids_by_component={}, vulnerabilities_by_id={})


def test_assembles_components_with_directness_and_bom_identity() -> None:
    bundle = assemble_bundle("APP@1", _BOM, acquire=_no_findings)

    directness = {c["name"]: c["directness"] for c in bundle.components}
    assert directness == {"app": "unknown", "requests": "direct", "urllib3": "transitive"}
    assert bundle.anchor_entity_id == "APP@1"
    assert bundle.bom_serial == "urn:uuid:abc"
    assert bundle.bom_version == "3"
    assert bundle.bom_digest


def test_generated_request_ids_are_unique_and_digest_excludes_them() -> None:
    first = assemble_bundle("APP@1", _BOM, acquire=_no_findings)
    second = assemble_bundle("APP@1", _BOM, acquire=_no_findings)

    assert first.request_id != second.request_id
    # The idempotency digest covers the payload only, so two assemblies of the
    # same BOM are recognisably the same submission.
    assert first.payload_digest() == second.payload_digest()


def test_explicit_request_id_is_preserved() -> None:
    bundle = assemble_bundle("APP@1", _BOM, acquire=_no_findings, request_id="req-7")

    assert bundle.request_id == "req-7"


def test_supplied_advisories_become_applicable_findings() -> None:
    record = {
        "id": "OSV-URLLIB",
        "affected": [{
            "package": {"purl": "pkg:pypi/urllib3"},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "1.26.5"}]}],
        }],
        "severity": [{"type": "CVSS_V3",
                      "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}],
    }

    bundle = assemble_bundle(
        "APP@1", _BOM,
        acquire=lambda queryable: acquisition_from_records(queryable, [record]),
    )

    assert len(bundle.findings) == 1
    finding = bundle.findings[0]
    assert finding["component_id"] == "indirect"
    assert finding["external_ids"] == ["OSV-URLLIB"]
    assert finding["applicability"] == "applicable"
    assert finding["severity_band"] == "critical"


def test_not_applicable_advisories_are_excluded_and_counted() -> None:
    record = {
        "id": "OSV-OLD",
        "affected": [{
            "package": {"purl": "pkg:pypi/urllib3"},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "1.0.0"}]}],
        }],
    }

    bundle = assemble_bundle(
        "APP@1", _BOM,
        acquire=lambda queryable: acquisition_from_records(queryable, [record]),
    )

    assert bundle.findings == ()
    assert bundle.diagnostics["not_applicable_excluded"] == 1


def test_root_component_is_never_queried_as_a_dependency() -> None:
    seen: list[Sequence[Mapping[str, str]]] = []

    def _capture(queryable: Sequence[Mapping[str, str]]) -> AcquisitionInputs:
        seen.append(list(queryable))
        return AcquisitionInputs(vulnerability_ids_by_component={}, vulnerabilities_by_id={})

    assemble_bundle("APP@1", _BOM, acquire=_capture)

    assert [q["component_id"] for q in seen[0]] == ["direct", "indirect"]
