"""The connection-side mirror of the effective-attribute-schema tests: a connection type's
base metadata schema merged with its specialization's contribution, including bound named
profiles. The pipeline is shared with entities, so these tests exist to pin the symmetry —
if the connection side ever resolved differently, a profile would mean two things.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifacts.schema import (
    clear_schema_cache,
    compute_effective_connection_metadata_schema,
    find_orphan_attachment_schemata,
    list_schema_files,
)
from src.domain.ontology_representation.profile_registry import profile_registry_from_mapping
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo


def _write_schema(repo_root: Path, filename: str, schema: dict) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / filename).write_text(json.dumps(schema), encoding="utf-8")


def setup_function() -> None:
    clear_schema_cache()


def _catalog(*, bound: tuple[str, ...] = (), attributes: dict | None = None) -> SpecializationCatalog:
    return SpecializationCatalog(
        (
            SpecializationInfo(
                slug="deployment-flow", name="Deployment Flow", concept_kind="connection",
                parent_type="flow", module_alias="archimate-4",
                bound_profiles=bound, attributes=attributes or {},
            ),
        )
    )


class TestFilenameClassification:
    def test_base_and_attachment_are_classified_apart(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {}})
        _write_schema(tmp_path, "connection-metadata.flow.deployment-flow.schema.json", {"properties": {}})
        by_name = {ref.filename: ref for ref in list_schema_files(tmp_path)}
        base = by_name["connection-metadata.flow.schema.json"]
        attachment = by_name["connection-metadata.flow.deployment-flow.schema.json"]
        assert (base.kind, base.subject, base.specialization_slug) == ("connection-metadata", "flow", "")
        assert attachment.kind == "connection-specialization-attachment"
        assert (attachment.subject, attachment.specialization_slug) == ("flow", "deployment-flow")

    def test_a_third_segment_matches_no_convention(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.a.b.schema.json", {"properties": {}})
        assert [ref.kind for ref in list_schema_files(tmp_path)] == ["unrecognized"]


class TestComputeEffectiveConnectionMetadataSchema:
    def test_nothing_declared_is_a_free_schema(self, tmp_path: Path) -> None:
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", [], specialization_catalog=SpecializationCatalog.empty(),
        )
        assert schema is None
        assert conflicts == []

    def test_base_only_when_no_specialization(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {"cadence": {"type": "string"}}})
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", [], specialization_catalog=SpecializationCatalog.empty(),
        )
        assert conflicts == []
        assert schema is not None
        assert set(schema["properties"]) == {"cadence"}

    @pytest.mark.verifies("REQ@1712870400.6ZR3nk")
    def test_specialization_inline_attributes_merge_in(self, tmp_path: Path) -> None:
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"],
            specialization_catalog=_catalog(attributes={"channel": {"type": "string", "level": "recommended"}}),
        )
        assert conflicts == []
        assert schema is not None
        assert schema["x-recommended"] == ["channel"]

    def test_attachment_file_merges_in(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path,
            "connection-metadata.flow.deployment-flow.schema.json",
            {"properties": {"pipeline": {"type": "string"}}},
        )
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"], specialization_catalog=_catalog(),
        )
        assert conflicts == []
        assert schema is not None
        assert "pipeline" in schema["properties"]

    def test_attachment_is_absent_when_the_specialization_is_not_applied(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {"cadence": {"type": "string"}}})
        _write_schema(
            tmp_path,
            "connection-metadata.flow.deployment-flow.schema.json",
            {"properties": {"pipeline": {"type": "string"}}},
        )
        schema, _ = compute_effective_connection_metadata_schema(
            tmp_path, "flow", [], specialization_catalog=_catalog(),
        )
        assert schema is not None
        assert set(schema["properties"]) == {"cadence"}

    def test_incompatible_base_and_specialization_property_is_a_conflict(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {"scope": {"type": "string"}}})
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"],
            specialization_catalog=_catalog(attributes={"scope": {"type": "integer"}}),
        )
        assert len(conflicts) == 1
        assert "scope" in conflicts[0]

    def test_an_entity_specialization_of_the_same_slug_does_not_leak_in(self, tmp_path: Path) -> None:
        # The catalog is keyed by concept kind; a connection lookup must not find an entity
        # specialization that happens to share the slug and parent-type name.
        entity_catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="deployment-flow", name="Deployment Flow", concept_kind="entity",
                    parent_type="flow", module_alias="archimate-4",
                    attributes={"channel": {"type": "string"}},
                ),
            )
        )
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"], specialization_catalog=entity_catalog,
        )
        assert conflicts == []
        assert schema is None


class TestNamedProfilesOnConnections:
    """A profile is a profile whichever concept kind binds it (PLAN §3 P2 order)."""

    def test_own_profile_overrides_bound_profile_overrides_base(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {"tier": {"type": "string"}}})
        registry = profile_registry_from_mapping(
            {
                "profile_schema": 1,
                "profiles": {"shared": {"version": 1, "attributes": {"Supplier": {"type": "string"}}}},
            },
            label="test",
        )
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"],
            specialization_catalog=_catalog(
                bound=("shared",), attributes={"Cadence": {"type": "string", "level": "required"}}
            ),
            profile_registry=registry,
        )
        assert conflicts == []
        assert schema is not None
        assert set(schema["properties"]) == {"tier", "Supplier", "Cadence"}
        assert schema["required"] == ["Cadence"]

    def test_incompatible_bound_profile_type_is_a_conflict(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {"Score": {"type": "string"}}})
        registry = profile_registry_from_mapping(
            {"profile_schema": 1, "profiles": {"metrics": {"version": 1, "attributes": {"Score": {"type": "number"}}}}},
            label="test",
        )
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"],
            specialization_catalog=_catalog(bound=("metrics",)), profile_registry=registry,
        )
        assert len(conflicts) == 1
        assert "Score" in conflicts[0]

    def test_undefined_bound_profile_is_left_unresolved_not_invented(self, tmp_path: Path) -> None:
        schema, conflicts = compute_effective_connection_metadata_schema(
            tmp_path, "flow", ["deployment-flow"], specialization_catalog=_catalog(bound=("does-not-exist",)),
        )
        assert conflicts == []
        assert schema is None


class TestOrphanConnectionAttachments:
    def test_attachment_with_declared_specialization_is_not_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.deployment-flow.schema.json", {"properties": {}})
        assert find_orphan_attachment_schemata(tmp_path, _catalog()) == []

    def test_attachment_with_unknown_specialization_is_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.ghost-flow.schema.json", {"properties": {}})
        assert find_orphan_attachment_schemata(tmp_path, SpecializationCatalog.empty()) == [
            "connection-metadata.flow.ghost-flow.schema.json"
        ]

    def test_base_connection_metadata_schema_is_never_orphan(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "connection-metadata.flow.schema.json", {"properties": {}})
        assert find_orphan_attachment_schemata(tmp_path, SpecializationCatalog.empty()) == []
