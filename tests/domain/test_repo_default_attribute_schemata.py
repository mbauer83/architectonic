"""Structural assertions for the shipped ArchiMate business-object + application-component
attribute schemata, that the two enums are single-sourced, and that a specialization
overlay resolves + merges through the existing effective-schema mechanism."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifacts.schema import clear_schema_cache, compute_effective_attribute_schema
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.repository.repo_default_attribute_schemata import (
    ARCHIMATE_ATTRIBUTE_SCHEMATA,
    LIFECYCLE_STATE_ENUM,
    SENSITIVITY_ENUM,
)
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA


def _schema(key: str) -> dict:
    return ARCHIMATE_ATTRIBUTE_SCHEMATA[key]


class TestShippedInDefaults:
    def test_all_four_schemata_are_merged_into_default_schemata(self) -> None:
        for key in ARCHIMATE_ATTRIBUTE_SCHEMATA:
            assert DEFAULT_SCHEMATA[key] is ARCHIMATE_ATTRIBUTE_SCHEMATA[key]

    def test_every_schema_is_non_strict_with_no_required_and_id_matches_key(self) -> None:
        for key, schema in ARCHIMATE_ATTRIBUTE_SCHEMATA.items():
            assert schema["$id"] == key
            assert schema["required"] == []
            assert schema["additionalProperties"] is True
            assert schema["type"] == "object"


class TestBusinessObjectSchema:
    def test_property_set_and_types(self) -> None:
        props = _schema("attributes.business-object.schema.json")["properties"]
        assert set(props) == {
            "Meaning", "Provenance", "Contained Information", "Internal Consistency Criteria",
            "External Consistency Criteria", "Sensitivity", "Lifecycle States",
        }
        assert props["Meaning"]["type"] == "string"
        assert props["Contained Information"] == {
            "type": "array", "items": {"type": "string"},
            "description": props["Contained Information"]["description"],
        }
        assert props["Sensitivity"]["enum"] == SENSITIVITY_ENUM
        assert props["Lifecycle States"]["type"] == "array"

    def test_sensitivity_description_documents_tlp_mapping(self) -> None:
        desc = _schema("attributes.business-object.schema.json")["properties"]["Sensitivity"]["description"]
        assert "TLP" in desc and "WHITE" in desc and "RED" in desc


class TestApplicationComponentSpecializations:
    def test_service_schema(self) -> None:
        props = _schema("attributes.application-component.service.schema.json")["properties"]
        assert set(props) == {
            "Programming Languages & Versions", "Frameworks & Versions", "Runtime Environments",
            "Communication Protocols & Versions", "Owner", "Source Repository", "Lifecycle State",
        }
        assert props["Programming Languages & Versions"]["type"] == "array"
        assert props["Source Repository"]["format"] == "uri"
        assert "Informative only" in props["Source Repository"]["description"]
        assert props["Lifecycle State"]["enum"] == LIFECYCLE_STATE_ENUM

    def test_module_and_endpoint_schemas(self) -> None:
        module = _schema("attributes.application-component.module.schema.json")["properties"]
        assert set(module) == {"Problem Domain", "Lifecycle State"}
        assert module["Lifecycle State"]["enum"] == LIFECYCLE_STATE_ENUM
        endpoint = _schema("attributes.application-component.endpoint.schema.json")["properties"]
        assert set(endpoint) == {"Communication Protocol & Version", "Authentication Method", "Lifecycle State"}
        assert endpoint["Lifecycle State"]["enum"] == LIFECYCLE_STATE_ENUM


class TestEnumsSingleSourced:
    def test_lifecycle_state_enum_object_identity_across_using_schemas(self) -> None:
        # All three application-component specializations reference the SAME enum list object.
        service = _schema("attributes.application-component.service.schema.json")["properties"]["Lifecycle State"]
        module = _schema("attributes.application-component.module.schema.json")["properties"]["Lifecycle State"]
        endpoint = _schema("attributes.application-component.endpoint.schema.json")["properties"]["Lifecycle State"]
        assert service["enum"] is LIFECYCLE_STATE_ENUM
        assert module["enum"] is LIFECYCLE_STATE_ENUM
        assert endpoint["enum"] is LIFECYCLE_STATE_ENUM

    def test_component_lifecycle_state_distinct_from_business_object_lifecycle_states(self) -> None:
        # The component enum (scalar) and the business-object list attribute are deliberately different.
        bo = _schema("attributes.business-object.schema.json")["properties"]
        assert "Lifecycle State" not in bo
        assert bo["Lifecycle States"]["type"] == "array"


class TestSpecializationOverlayResolves:
    def test_service_overlay_merges_via_effective_schema(self, tmp_path: Path) -> None:
        clear_schema_cache()
        schemata = tmp_path / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True)
        key = "attributes.application-component.service.schema.json"
        (schemata / key).write_text(json.dumps(ARCHIMATE_ATTRIBUTE_SCHEMATA[key]), encoding="utf-8")
        merged, conflicts = compute_effective_attribute_schema(
            tmp_path, "application-component", ["service"],
            specialization_catalog=SpecializationCatalog.empty(),
        )
        assert conflicts == []
        assert merged is not None
        assert "Owner" in merged["properties"]
        assert merged["properties"]["Lifecycle State"]["enum"] == LIFECYCLE_STATE_ENUM
