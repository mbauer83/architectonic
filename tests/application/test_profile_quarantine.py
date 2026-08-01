"""WU-Q2/Q3: Class B quarantine computation and the write-boundary gate's application core.

A quarantine arises when a bound named profile conflicts with the base schema (or another
bound profile) on an attribute's type. These tests inject the profile registry and a bound
specialization onto the real runtime catalogs via ``replace`` so no repo fixture is needed
for the pure computation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.application.artifacts.schema import clear_schema_cache
from src.application.profile_quarantine import (
    ProfileQuarantineError,
    assert_not_quarantined,
    compute_quarantine_set,
    pair_quarantine_conflicts,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.profile_registry import profile_registry_from_mapping
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo


def _spec(slug: str, bound: tuple[str, ...]) -> SpecializationInfo:
    return SpecializationInfo(
        slug=slug, name=slug.title(), concept_kind="entity",
        parent_type="application-component", module_alias="archimate-4", bound_profiles=bound,
    )


def _catalogs() -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    base = build_runtime_catalogs(build_module_registry())
    registry = profile_registry_from_mapping(
        {
            "profile_schema": 1,
            "profiles": {
                "metrics": {"version": 1, "attributes": {"Score": {"type": "number"}}},
                "ownership": {"version": 1, "attributes": {"Owner": {"type": "string"}}},
            },
        },
        label="test",
    )
    specs = SpecializationCatalog((_spec("service", ("metrics",)), _spec("module", ("ownership",))))
    return replace(base, specializations=specs, profiles=registry)


def _write_base(repo_root: Path, prop_type: str) -> None:
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / "attributes.application-component.schema.json").write_text(
        json.dumps({"properties": {"Score": {"type": prop_type}}}), encoding="utf-8"
    )


def setup_function() -> None:
    clear_schema_cache()


def test_conflicting_bound_profile_quarantines_the_pair(tmp_path: Path) -> None:
    _write_base(tmp_path, "string")  # base Score:string vs metrics Score:number => conflict
    conflicts = pair_quarantine_conflicts(
        tmp_path, "entity", "application-component", ["service"], catalogs=_catalogs()
    )
    assert [c.conflict_class for c in conflicts] == ["scoped"]
    assert "Score" in conflicts[0].message


def test_non_conflicting_pair_is_not_quarantined(tmp_path: Path) -> None:
    _write_base(tmp_path, "string")  # base has no Owner; ownership adds Owner:string => no conflict
    assert pair_quarantine_conflicts(
        tmp_path, "entity", "application-component", ["module"], catalogs=_catalogs()
    ) == ()


def test_quarantine_is_confined_to_the_affected_pair(tmp_path: Path) -> None:
    _write_base(tmp_path, "string")
    quarantined = compute_quarantine_set(tmp_path, _catalogs())
    assert ("entity", "application-component", "service") in quarantined
    # The sibling specialization of the SAME base type is unaffected.
    assert ("entity", "application-component", "module") not in quarantined


def test_assert_not_quarantined_raises_a_typed_error(tmp_path: Path) -> None:
    _write_base(tmp_path, "string")
    with pytest.raises(ProfileQuarantineError) as excinfo:
        assert_not_quarantined(tmp_path, "entity", "application-component", ["service"], catalogs=_catalogs())
    assert "quarantined" in str(excinfo.value)
    assert excinfo.value.specialization == "service"
    assert isinstance(excinfo.value, ValueError)  # so every transport surfaces it


def test_assert_not_quarantined_allows_a_clean_pair(tmp_path: Path) -> None:
    _write_base(tmp_path, "string")
    assert_not_quarantined(tmp_path, "entity", "application-component", ["module"], catalogs=_catalogs())


# ── Connection side (WU-W2): identical rules on the other concept kind ────────


def _connection_catalogs() -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    base = build_runtime_catalogs(build_module_registry())
    registry = profile_registry_from_mapping(
        {"profile_schema": 1, "profiles": {"metrics": {"version": 1, "attributes": {"Score": {"type": "number"}}}}},
        label="test",
    )
    specs = SpecializationCatalog(
        (
            SpecializationInfo(
                slug="deployment-flow", name="Deployment Flow", concept_kind="connection",
                parent_type="archimate-flow", module_alias="archimate-4", bound_profiles=("metrics",),
            ),
        )
    )
    return replace(base, specializations=specs, profiles=registry)


def _write_connection_base(repo_root: Path, prop_type: str) -> None:
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / "connection-metadata.archimate-flow.schema.json").write_text(
        json.dumps({"properties": {"Score": {"type": prop_type}}}), encoding="utf-8"
    )


def test_conflicting_bound_profile_quarantines_a_connection_pair(tmp_path: Path) -> None:
    _write_connection_base(tmp_path, "string")  # base Score:string vs metrics Score:number
    conflicts = pair_quarantine_conflicts(
        tmp_path, "connection", "archimate-flow", ["deployment-flow"], catalogs=_connection_catalogs()
    )
    assert [c.conflict_class for c in conflicts] == ["scoped"]
    assert "Score" in conflicts[0].message


def test_clean_connection_pair_is_not_quarantined(tmp_path: Path) -> None:
    _write_connection_base(tmp_path, "number")  # agrees with the bound profile
    assert pair_quarantine_conflicts(
        tmp_path, "connection", "archimate-flow", ["deployment-flow"], catalogs=_connection_catalogs()
    ) == ()


def test_assert_not_quarantined_refuses_a_connection_pair(tmp_path: Path) -> None:
    _write_connection_base(tmp_path, "string")
    with pytest.raises(ProfileQuarantineError) as excinfo:
        assert_not_quarantined(
            tmp_path, "connection", "archimate-flow", ["deployment-flow"], catalogs=_connection_catalogs()
        )
    assert excinfo.value.concept_kind == "connection"
    assert excinfo.value.specialization == "deployment-flow"


def test_quarantine_set_covers_both_concept_kinds(tmp_path: Path) -> None:
    _write_connection_base(tmp_path, "string")
    quarantined = compute_quarantine_set(tmp_path, _connection_catalogs())
    assert ("connection", "archimate-flow", "deployment-flow") in quarantined
