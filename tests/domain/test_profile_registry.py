"""Unit tests for the named-profile registry format, version guard, and merge."""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.profile_registry import (
    PROFILE_SCHEMA_VERSION,
    ProfileRegistry,
    ProfileRegistryError,
    classify_profile_conflicts,
    merge_profile_registries,
    profile_registry_from_mapping,
    unresolved_profile_bindings,
)
from src.domain.ontology_representation.profiles import merge_property_schemas


def _registry(**profiles: int):
    return profile_registry_from_mapping(
        {"profile_schema": 1, "profiles": {name: {"version": v} for name, v in profiles.items()}},
        label="test",
    )


def _valid_mapping() -> dict[str, object]:
    return {
        "profile_schema": 1,
        "profiles": {
            "supplier-info": {
                "version": 2,
                "attributes": {
                    "Supplier": {"type": "string", "level": "required"},
                    "Rating": {"type": "number"},
                },
            }
        },
    }


def test_valid_registry_loads_with_versions_and_attributes() -> None:
    registry = profile_registry_from_mapping(_valid_mapping(), label="test")
    assert registry.profile_schema == 1
    profile = registry.get("supplier-info")
    assert profile is not None
    assert profile.version == 2
    names = {attr.name: attr for attr in profile.definition.attributes}
    assert names["Supplier"].level == "required"
    assert names["Rating"].type == "number"


def test_absent_profiles_key_is_a_valid_empty_registry() -> None:
    registry = profile_registry_from_mapping({"profile_schema": 1}, label="test")
    assert dict(registry.profiles) == {}


def test_empty_registry_is_the_no_named_profiles_state() -> None:
    empty = ProfileRegistry.empty()
    assert empty.profile_schema == PROFILE_SCHEMA_VERSION
    assert empty.get("anything") is None


def test_unknown_profile_schema_is_rejected() -> None:
    with pytest.raises(ProfileRegistryError, match="unsupported profile_schema 99"):
        profile_registry_from_mapping({"profile_schema": 99, "profiles": {}}, label="bad.yaml")


def test_missing_profile_schema_is_rejected() -> None:
    with pytest.raises(ProfileRegistryError, match="'profile_schema' is required"):
        profile_registry_from_mapping({"profiles": {}}, label="bad.yaml")


def test_non_integer_profile_schema_is_rejected() -> None:
    with pytest.raises(ProfileRegistryError, match="profile_schema must be an integer"):
        profile_registry_from_mapping({"profile_schema": "1"}, label="bad.yaml")
    # A bool is not an acceptable integer version.
    with pytest.raises(ProfileRegistryError, match="profile_schema must be an integer"):
        profile_registry_from_mapping({"profile_schema": True}, label="bad.yaml")


def test_profile_missing_version_is_rejected() -> None:
    raw = {"profile_schema": 1, "profiles": {"p": {"attributes": {}}}}
    with pytest.raises(ProfileRegistryError, match="profile 'p' is missing 'version'"):
        profile_registry_from_mapping(raw, label="bad.yaml")


def test_non_mapping_registry_is_rejected() -> None:
    with pytest.raises(ProfileRegistryError, match="registry must be a mapping"):
        profile_registry_from_mapping(["not", "a", "mapping"], label="bad.yaml")


def test_error_label_names_the_source() -> None:
    with pytest.raises(ProfileRegistryError) as excinfo:
        profile_registry_from_mapping({}, label="/repo/.arch-repo/profiles.yaml")
    assert str(excinfo.value).startswith("/repo/.arch-repo/profiles.yaml:")
    assert excinfo.value.label == "/repo/.arch-repo/profiles.yaml"


def test_merge_unions_disjoint_registries() -> None:
    a = profile_registry_from_mapping({"profile_schema": 1, "profiles": {"a": {"version": 1}}}, label="a")
    b = profile_registry_from_mapping({"profile_schema": 1, "profiles": {"b": {"version": 1}}}, label="b")
    merged = merge_profile_registries([a, b])
    assert set(merged.profiles) == {"a", "b"}


def test_merge_rejects_a_duplicate_name_across_registries() -> None:
    a = profile_registry_from_mapping({"profile_schema": 1, "profiles": {"dup": {"version": 1}}}, label="a")
    b = profile_registry_from_mapping({"profile_schema": 1, "profiles": {"dup": {"version": 2}}}, label="b")
    with pytest.raises(ProfileRegistryError, match="'dup' is defined more than once"):
        merge_profile_registries([a, b])


# --- WU-P4: conflict classification -----------------------------------------------------

_REGISTRY = profile_registry_from_mapping(
    {"profile_schema": 1, "profiles": {"known": {"version": 1, "attributes": {"X": {"type": "string"}}}}},
    label="test",
)


def test_undefined_binding_is_a_structural_conflict() -> None:
    conflicts = classify_profile_conflicts(["known", "ghost"], _REGISTRY, [])
    assert [(c.conflict_class, "ghost" in c.message) for c in conflicts] == [("structural", True)]


def test_defined_binding_is_not_a_conflict() -> None:
    assert classify_profile_conflicts(["known"], _REGISTRY, []) == ()


def test_identical_redefinition_is_not_a_conflict() -> None:
    # Two fragments declaring the same attribute+type compose with no merge conflict, so
    # classification reports nothing scoped.
    _merged, merge_conflicts = merge_property_schemas(
        [{"properties": {"Supplier": {"type": "string"}}}, {"properties": {"Supplier": {"type": "string"}}}]
    )
    assert merge_conflicts == []
    assert classify_profile_conflicts([], _REGISTRY, merge_conflicts) == ()


def test_incompatible_type_redefinition_is_a_scoped_conflict() -> None:
    _merged, merge_conflicts = merge_property_schemas(
        [{"properties": {"Supplier": {"type": "string"}}}, {"properties": {"Supplier": {"type": "number"}}}]
    )
    assert len(merge_conflicts) == 1
    conflicts = classify_profile_conflicts([], _REGISTRY, merge_conflicts)
    assert [c.conflict_class for c in conflicts] == ["scoped"]


def test_both_classes_are_assigned_in_one_pass() -> None:
    _merged, merge_conflicts = merge_property_schemas(
        [{"properties": {"S": {"type": "string"}}}, {"properties": {"S": {"type": "integer"}}}]
    )
    conflicts = classify_profile_conflicts(["ghost"], _REGISTRY, merge_conflicts)
    assert {c.conflict_class for c in conflicts} == {"structural", "scoped"}
    # Structural is reported first (it subsumes the scoped one: the schema is indeterminable).
    assert conflicts[0].conflict_class == "structural"


# --- overlay + undefined-binding detection (WU-Q1 helpers) -------------------------------


def test_overlay_lets_repo_override_shipped_by_name() -> None:
    shipped = _registry(shared=1, only_shipped=1)
    repo = _registry(shared=9, only_repo=1)
    effective = shipped.overlay(repo)
    assert effective.get("shared").version == 9  # repo wins
    assert effective.get("only_shipped") is not None
    assert effective.get("only_repo") is not None


def test_unresolved_bindings_reports_only_undefined_names() -> None:
    registry = _registry(known=1)
    bindings = [("spec app/service", ("known", "ghost")), ("spec app/module", ("known",))]
    findings = unresolved_profile_bindings(bindings, registry)
    assert len(findings) == 1
    assert "ghost" in findings[0] and "spec app/service" in findings[0]


def test_unresolved_bindings_clean_when_all_defined() -> None:
    assert unresolved_profile_bindings([("s", ("known",))], _registry(known=1)) == ()
