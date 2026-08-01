"""Tests for the D13 effective-attribute-schema computation (base-type schema ⊕ an entity's
own specialization's profile) and the orphan-attachment-schema detector, plus an
integration test proving `check_attribute_schema` reports the merge conflict (E043) and
validates a specialized entity against its merged schema."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifacts.schema import (
    clear_schema_cache,
    compute_effective_attribute_schema,
    find_orphan_attachment_schemata,
)
from src.application.verification._verifier_rules_schema import check_attribute_schema
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.ontology_representation.profile_registry import profile_registry_from_mapping
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo

_FAKE_PATH = Path("/tmp/entity.md")


def _fresh_result() -> VerificationResult:
    return VerificationResult(path=_FAKE_PATH, file_type="entity")


def _write_schema(repo_root: Path, filename: str, schema: dict) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / filename).write_text(json.dumps(schema), encoding="utf-8")


def setup_function() -> None:
    clear_schema_cache()


class TestComputeEffectiveAttributeSchema:
    def test_no_base_no_specialization_is_none(self, tmp_path: Path) -> None:
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "requirement", [],
            specialization_catalog=SpecializationCatalog.empty(),
        )
        assert schema is None
        assert conflicts == []

    def test_base_only_when_no_specialization(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.requirement.schema.json", {"properties": {"rationale": {"type": "string"}}})
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "requirement", [],
            specialization_catalog=SpecializationCatalog.empty(),
        )
        assert conflicts == []
        assert schema is not None
        assert set(schema["properties"]) == {"rationale"}

    def test_specialization_inline_attributes_merge_in(self, tmp_path: Path) -> None:
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"criticality": {"type": "string", "level": "recommended"}},
                ),
            )
        )
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "collaboration", ["business-collaboration"],
            specialization_catalog=spec_catalog,
        )
        assert conflicts == []
        assert schema is not None
        assert schema["x-recommended"] == ["criticality"]

    def test_attachment_file_merges_in(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path,
            "attributes.collaboration.business-collaboration.schema.json",
            {"properties": {"owner": {"type": "string"}}},
        )
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                ),
            )
        )
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "collaboration", ["business-collaboration"],
            specialization_catalog=spec_catalog,
        )
        assert conflicts == []
        assert schema is not None
        assert "owner" in schema["properties"]

    def test_incompatible_base_and_specialization_property_is_a_conflict(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}})
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"scope": {"type": "integer"}},
                ),
            )
        )
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "collaboration", ["business-collaboration"],
            specialization_catalog=spec_catalog,
        )
        assert len(conflicts) == 1
        assert "scope" in conflicts[0]


class TestNamedProfileResolution:
    """WU-P3: bound named profiles resolve between the base schema and a specialization's
    own profile (PLAN §3 P2 order)."""

    def _catalog(self, *, bound: tuple[str, ...], attributes: dict) -> SpecializationCatalog:
        return SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="service", name="Service", concept_kind="entity",
                    parent_type="application-component", module_alias="archimate-4",
                    bound_profiles=bound, attributes=attributes,
                ),
            )
        )

    def test_specialization_own_profile_overrides_bound_profile_overrides_base(self, tmp_path: Path) -> None:
        # base: token=string ; bound profile: token=string(default shared) ; spec own: token wins as an enum default.
        _write_schema(
            tmp_path, "attributes.application-component.schema.json", {"properties": {"tier": {"type": "string"}}}
        )
        registry = profile_registry_from_mapping(
            {
                "profile_schema": 1,
                "profiles": {"shared": {"version": 1, "attributes": {"Supplier": {"type": "string"}}}},
            },
            label="test",
        )
        catalog = self._catalog(bound=("shared",), attributes={"Cadence": {"type": "string", "level": "required"}})
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "application-component", ["service"],
            specialization_catalog=catalog, profile_registry=registry,
        )
        assert conflicts == []
        assert schema is not None
        # base + bound profile + own profile all present, in one merged schema.
        assert set(schema["properties"]) == {"tier", "Supplier", "Cadence"}
        assert schema["required"] == ["Cadence"]

    def test_parent_attribute_inheritance_still_works(self, tmp_path: Path) -> None:
        # Regression: the base-type schema (fragment 1) still contributes with no bound profiles.
        _write_schema(
            tmp_path, "attributes.application-component.schema.json", {"properties": {"tier": {"type": "string"}}}
        )
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "application-component", [],
            specialization_catalog=SpecializationCatalog.empty(),
        )
        assert conflicts == []
        assert schema is not None
        assert set(schema["properties"]) == {"tier"}

    def test_incompatible_bound_profile_type_is_a_class_b_conflict(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path, "attributes.application-component.schema.json", {"properties": {"Score": {"type": "string"}}}
        )
        registry = profile_registry_from_mapping(
            {"profile_schema": 1, "profiles": {"metrics": {"version": 1, "attributes": {"Score": {"type": "number"}}}}},
            label="test",
        )
        catalog = self._catalog(bound=("metrics",), attributes={})
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "application-component", ["service"],
            specialization_catalog=catalog, profile_registry=registry,
        )
        assert len(conflicts) == 1
        assert "Score" in conflicts[0]

    def test_undefined_bound_profile_is_left_unresolved_not_invented(self, tmp_path: Path) -> None:
        # A name with no registry entry contributes nothing here (Class A is a startup check).
        catalog = self._catalog(bound=("does-not-exist",), attributes={})
        schema, conflicts = compute_effective_attribute_schema(
            tmp_path, "application-component", ["service"],
            specialization_catalog=catalog,
        )
        assert conflicts == []
        assert schema is None  # no base, no resolvable profile, no attachment


class TestFindOrphanAttachmentSchemata:
    def test_no_schemata_dir_is_empty(self, tmp_path: Path) -> None:
        assert find_orphan_attachment_schemata(tmp_path, SpecializationCatalog.empty()) == []

    def test_base_type_schema_is_never_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.requirement.schema.json", {"properties": {}})
        assert find_orphan_attachment_schemata(tmp_path, SpecializationCatalog.empty()) == []

    def test_attachment_with_declared_specialization_is_not_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.business-collaboration.schema.json", {"properties": {}})
        catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                ),
            )
        )
        assert find_orphan_attachment_schemata(tmp_path, catalog) == []

    def test_attachment_with_unknown_specialization_is_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.ghost-collaboration.schema.json", {"properties": {}})
        assert find_orphan_attachment_schemata(tmp_path, SpecializationCatalog.empty()) == [
            "attributes.collaboration.ghost-collaboration.schema.json"
        ]


class TestCheckAttributeSchemaWithSpecialization:
    def test_reports_e043_on_conflicting_merge(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}})
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"scope": {"type": "integer"}},
                ),
            )
        )
        content = "## Properties\n\n| Attribute | Value |\n|---|---|\n| scope | team |\n"
        fm = {"artifact-type": "collaboration", "specialization": "business-collaboration"}
        result = _fresh_result()

        check_attribute_schema(
            content, fm, tmp_path, result, "test",
            specialization_catalog=spec_catalog,
        )

        assert [i.code for i in result.issues] == ["E043"]

    def test_specialized_entity_validates_against_merged_schema(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}})
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"cadence": {"type": "string", "level": "required"}},
                ),
            )
        )
        content = "## Properties\n\n| Attribute | Value |\n|---|---|\n| scope | team |\n| cadence | weekly |\n"
        fm = {"artifact-type": "collaboration", "specialization": "business-collaboration"}
        result = _fresh_result()

        check_attribute_schema(
            content, fm, tmp_path, result, "test",
            specialization_catalog=spec_catalog,
        )

        assert result.issues == []

    def test_missing_specialization_required_attribute_is_a_warning(self, tmp_path: Path) -> None:
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"cadence": {"type": "string", "level": "required"}},
                ),
            )
        )
        content = "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n"
        fm = {"artifact-type": "collaboration", "specialization": "business-collaboration"}
        result = _fresh_result()

        check_attribute_schema(
            content, fm, tmp_path, result, "test",
            specialization_catalog=spec_catalog,
        )

        assert [i.code for i in result.issues] == ["W042"]

    def test_missing_recommended_attribute_is_a_warning_not_silently_ignored(self, tmp_path: Path) -> None:
        spec_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                    attributes={"criticality": {"type": "string", "level": "recommended"}},
                ),
            )
        )
        content = "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n"
        fm = {"artifact-type": "collaboration", "specialization": "business-collaboration"}
        result = _fresh_result()

        check_attribute_schema(
            content, fm, tmp_path, result, "test",
            specialization_catalog=spec_catalog,
        )

        assert [i.code for i in result.issues] == ["W042"]
        assert "criticality" in result.issues[0].message
