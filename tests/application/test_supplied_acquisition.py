"""Caller-supplied OSV records → AcquisitionInputs: package-identity matching by
purl and by ecosystem/name, version-independence, fan-out to several components,
and honest diagnostics for records that match nothing."""

from __future__ import annotations

from typing import Any

from src.application.security_signals.supplied_acquisition import acquisition_from_records

_QUERYABLE = [
    {"component_id": "pkg:pypi/requests@2.31.0", "purl": "pkg:pypi/requests@2.31.0"},
    {"component_id": "npm-lodash", "purl": "pkg:npm/lodash@4.17.20"},
    {"component_id": "scoped", "purl": "pkg:npm/%40scope/thing@1.0.0"},
]


def _record(record_id: str, packages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": record_id, "affected": [{"package": p} for p in packages]}


def test_matches_by_purl_identity_ignoring_version() -> None:
    # The advisory names a different version of the same package: identity still
    # matches — version-range applicability is decided downstream, not here.
    acquisition = acquisition_from_records(
        _QUERYABLE, [_record("OSV-1", [{"purl": "pkg:pypi/requests@1.0.0"}])])

    assert acquisition.vulnerability_ids_by_component == {
        "pkg:pypi/requests@2.31.0": ["OSV-1"]}
    assert acquisition.vulnerabilities_by_id["OSV-1"]["id"] == "OSV-1"
    assert list(acquisition.unmatched_components) == []


def test_matches_by_ecosystem_and_name_when_no_purl() -> None:
    acquisition = acquisition_from_records(
        _QUERYABLE, [_record("GHSA-x", [{"ecosystem": "npm", "name": "lodash"}])])

    assert acquisition.vulnerability_ids_by_component == {"npm-lodash": ["GHSA-x"]}


def test_matches_namespaced_ecosystem_name() -> None:
    acquisition = acquisition_from_records(
        _QUERYABLE, [_record("GHSA-y", [{"ecosystem": "npm", "name": "@scope/thing"}])])

    assert acquisition.vulnerability_ids_by_component == {"scoped": ["GHSA-y"]}


def test_one_record_fans_out_to_every_matching_component() -> None:
    queryable = [
        {"component_id": "a", "purl": "pkg:pypi/requests@2.31.0"},
        {"component_id": "b", "purl": "pkg:pypi/requests@2.20.0"},
    ]

    acquisition = acquisition_from_records(
        queryable, [_record("OSV-2", [{"purl": "pkg:pypi/requests"}])])

    assert acquisition.vulnerability_ids_by_component == {"a": ["OSV-2"], "b": ["OSV-2"]}


def test_record_matching_nothing_is_a_diagnostic_not_a_finding() -> None:
    acquisition = acquisition_from_records(
        _QUERYABLE, [_record("OSV-3", [{"purl": "pkg:pypi/absent"}])])

    assert acquisition.vulnerability_ids_by_component == {}
    assert acquisition.vulnerabilities_by_id == {}
    assert len(acquisition.unmatched_components) == 1
    assert "OSV-3" in acquisition.unmatched_components[0]["reason"]


def test_record_without_id_is_reported() -> None:
    acquisition = acquisition_from_records(_QUERYABLE, [{"affected": []}])

    assert acquisition.unmatched_components[0]["reason"] == "record has no id"


def test_duplicate_affected_entries_yield_one_id_per_component() -> None:
    record = _record("OSV-4", [
        {"purl": "pkg:pypi/requests@1.0.0"},
        {"ecosystem": "PyPI", "name": "requests"},
    ])

    acquisition = acquisition_from_records(_QUERYABLE, [record])

    assert acquisition.vulnerability_ids_by_component == {
        "pkg:pypi/requests@2.31.0": ["OSV-4"]}


def test_unparsable_and_unknown_packages_are_ignored_safely() -> None:
    acquisition = acquisition_from_records(_QUERYABLE, [
        _record("OSV-5", [{"purl": "not-a-purl"}]),
        _record("OSV-6", [{"ecosystem": "SomeDistro", "name": "thing"}]),
    ])

    assert acquisition.vulnerability_ids_by_component == {}
    assert len(acquisition.unmatched_components) == 2
