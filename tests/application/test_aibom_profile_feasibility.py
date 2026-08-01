"""WU-U1: prove the AIBOM plan's D3/D3a design executes on the landed named-profile
registry, so the AIBOM stream is unblocked.

D3  — shared attributes come from ONE named `ai-provenance` profile bound to the AI
      specializations (across different base types), plus a small per-specialization profile
      for what genuinely differs.
D3a — AIBOM profiles do NOT redeclare attributes the base type already provides; base-type
      inheritance already delivers them.

These are executable confirmations against `compute_effective_attribute_schema`, not prose:
if the registry could not carry this shape, one of these would fail.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifacts.schema import clear_schema_cache, compute_effective_attribute_schema
from src.domain.ontology_representation.profile_registry import profile_registry_from_mapping
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo


def _write_base(repo_root: Path, artifact_type: str, schema: dict) -> None:
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / f"attributes.{artifact_type}.schema.json").write_text(json.dumps(schema), encoding="utf-8")


def _registry():
    # One shared provenance profile + one small per-spec profile — the D3 shape.
    return profile_registry_from_mapping(
        {
            "profile_schema": 1,
            "profiles": {
                "ai-provenance": {
                    "version": 1,
                    "attributes": {
                        "Model Provider": {"type": "string"},
                        "Licenses": {"type": "array"},
                    },
                },
                "ai-model-card": {
                    "version": 1,
                    "attributes": {"Architecture Family": {"type": "string"}},
                },
            },
        },
        label="test",
    )


def _catalog() -> SpecializationCatalog:
    # ai-model (application-component) and ai-dataset (data-object) both bind ai-provenance.
    return SpecializationCatalog(
        (
            SpecializationInfo(
                slug="ai-model", name="AI Model", concept_kind="entity",
                parent_type="application-component", module_alias="archimate-4",
                bound_profiles=("ai-provenance", "ai-model-card"),
            ),
            SpecializationInfo(
                slug="ai-dataset", name="AI Dataset", concept_kind="entity",
                parent_type="data-object", module_alias="archimate-4",
                bound_profiles=("ai-provenance",),
            ),
        )
    )


def setup_function() -> None:
    clear_schema_cache()


def test_one_shared_profile_binds_to_specializations_across_base_types(tmp_path: Path) -> None:
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "application-component", ["ai-model"],
        specialization_catalog=_catalog(), profile_registry=_registry(),
    )
    assert conflicts == []
    assert schema is not None
    # Shared provenance + this spec's own card attribute, all merged once.
    assert {"Model Provider", "Licenses", "Architecture Family"} <= set(schema["properties"])


def test_the_same_shared_profile_serves_a_different_base_type(tmp_path: Path) -> None:
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "data-object", ["ai-dataset"],
        specialization_catalog=_catalog(), profile_registry=_registry(),
    )
    assert conflicts == []
    assert schema is not None
    # The dataset gets provenance but NOT the model-card attribute it never bound.
    assert {"Model Provider", "Licenses"} <= set(schema["properties"])
    assert "Architecture Family" not in schema["properties"]


def test_base_attributes_are_inherited_without_redeclaration(tmp_path: Path) -> None:
    # D3a: the base data-object provides Sensitivity/Provenance; the AI profile declares only
    # what is new. The effective schema carries both, with no conflict — inheritance works,
    # so AIBOM profiles need not (and must not) redeclare them.
    _write_base(
        tmp_path, "data-object",
        {"properties": {"Sensitivity": {"type": "string"}, "Provenance": {"type": "string"}}},
    )
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "data-object", ["ai-dataset"],
        specialization_catalog=_catalog(), profile_registry=_registry(),
    )
    assert conflicts == []
    assert schema is not None
    assert {"Sensitivity", "Provenance", "Model Provider", "Licenses"} <= set(schema["properties"])


def test_redeclaring_an_inherited_attribute_with_a_clashing_type_is_a_conflict(tmp_path: Path) -> None:
    # The guardrail behind D3a: if an AIBOM profile DID redeclare an inherited attribute with a
    # different type, the merge reports it — the mistake cannot pass silently.
    _write_base(tmp_path, "data-object", {"properties": {"Sensitivity": {"type": "string"}}})
    registry = profile_registry_from_mapping(
        {"profile_schema": 1, "profiles": {"bad": {"version": 1, "attributes": {"Sensitivity": {"type": "number"}}}}},
        label="test",
    )
    catalog = SpecializationCatalog(
        (
            SpecializationInfo(
                slug="ai-dataset", name="AI Dataset", concept_kind="entity",
                parent_type="data-object", module_alias="archimate-4", bound_profiles=("bad",),
            ),
        )
    )
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "data-object", ["ai-dataset"], specialization_catalog=catalog, profile_registry=registry,
    )
    assert any("Sensitivity" in message for message in conflicts)
