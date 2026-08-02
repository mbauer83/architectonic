from __future__ import annotations

import pytest

from src.domain.guidance.guidance import GuidanceEntry, GuidanceKey, GuidanceOverlay
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    specialization_catalog_from_mapping,
)
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, META_ONTOLOGY_ALIAS, load_archimate_4_module


class TestArchimate4SpecializationLibrary:
    @pytest.mark.verifies("REQ@1777369240.dGaLkH")
    def test_module_loads_informative_entity_and_connection_library(self) -> None:
        module = load_archimate_4_module(_PACKAGE_DIR)
        catalog = module.specialization_catalog

        business_service = catalog.get("entity", "service", "business-service", module_alias=META_ONTOLOGY_ALIAS)
        assert business_service is not None
        assert business_service.name == "Business Service"
        assert business_service.create_when == ""
        assert business_service.never_create_when == ""

        business_collaboration = catalog.get(
            "entity", "collaboration", "business-collaboration", module_alias=META_ONTOLOGY_ALIAS
        )
        assert business_collaboration is not None
        assert business_collaboration.name == "Business Collaboration"

        assignment_specs = {
            spec.slug
            for spec in catalog.for_type(
                "connection",
                "archimate-assignment",
                module_alias=META_ONTOLOGY_ALIAS,
            )
        }
        assert {"responsibility-assignment", "behavior-assignment"} <= assignment_specs

        component_specs = {
            spec.slug
            for spec in catalog.for_type("entity", "application-component", module_alias=META_ONTOLOGY_ALIAS)
        }
        assert {"service", "module", "endpoint"} <= component_specs

    @pytest.mark.verifies("REQ@1777369240.dGaLkH")
    def test_guidance_overlay_applies_to_entity_and_connection_specializations(self) -> None:
        overlay = GuidanceOverlay(
            {
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS,
                    concept_kind="entity",
                    type_name="service",
                    specialization="business-service",
                ): GuidanceEntry(create_when="entity-create", never_create_when="entity-never"),
                GuidanceKey(
                    module_alias=META_ONTOLOGY_ALIAS,
                    concept_kind="connection",
                    type_name="archimate-assignment",
                    specialization="responsibility-assignment",
                ): GuidanceEntry(create_when="connection-create", never_create_when="connection-never"),
            }
        )

        module = load_archimate_4_module(_PACKAGE_DIR, guidance=overlay)
        entity = module.specialization_catalog.get(
            "entity", "service", "business-service", module_alias=META_ONTOLOGY_ALIAS
        )
        connection = module.specialization_catalog.get(
            "connection", "archimate-assignment", "responsibility-assignment", module_alias=META_ONTOLOGY_ALIAS
        )

        assert entity is not None
        assert entity.create_when == "entity-create"
        assert entity.never_create_when == "entity-never"
        assert connection is not None
        assert connection.create_when == "connection-create"
        assert connection.never_create_when == "connection-never"

    def test_repo_specialization_duplicate_of_module_library_is_rejected(self) -> None:
        repo_catalog = specialization_catalog_from_mapping(
            {
                "specializations": {
                    "entity": {
                        "service": [
                            {
                                "slug": "business-service",
                                "name": "Custom Business Service",
                            }
                        ]
                    }
                }
            },
            module_alias=META_ONTOLOGY_ALIAS,
        )

        with pytest.raises(ValueError, match="Duplicate specialization"):
            load_archimate_4_module(_PACKAGE_DIR, specializations=repo_catalog)

    def test_ships_the_eight_ai_specializations_on_their_base_types(self) -> None:
        # WU-A1 (Q1 refined to EIGHT: ai-agent absorbs ai-orchestrator; ai-inference-service
        # specializes the `service` entity type, not the non-existent "application-service").
        module = load_archimate_4_module(_PACKAGE_DIR)
        catalog = module.specialization_catalog
        expected = {
            "application-component": {"ai-model", "ai-agent"},
            "service": {"ai-inference-service"},
            "data-object": {"ai-dataset", "ai-prompt-asset", "ai-vector-store"},
            "system-software": {"ai-runtime"},
            "application-interface": {"ai-tool-interface"},
        }
        for base_type, slugs in expected.items():
            have = {s.slug for s in catalog.for_type("entity", base_type, module_alias=META_ONTOLOGY_ALIAS)}
            assert slugs <= have, f"{base_type} missing {slugs - have}"
        # ai-orchestrator was merged away — it must NOT ship as a separate specialization.
        component = {
            s.slug for s in catalog.for_type("entity", "application-component", module_alias=META_ONTOLOGY_ALIAS)
        }
        assert "ai-orchestrator" not in component
        # Each carries authoring guidance (description + create/never), so the surfaces can
        # explain when to reach for it.
        model = catalog.get("entity", "application-component", "ai-model", module_alias=META_ONTOLOGY_ALIAS)
        assert model is not None
        assert model.name == "AI Model"
        assert model.description
        assert model.create_when and model.never_create_when

    def test_unknown_parent_type_is_rejected(self) -> None:
        repo_catalog = SpecializationCatalog(
            specialization_catalog_from_mapping(
                {
                    "specializations": {
                        "entity": {
                            "not-a-parent": [
                                {
                                    "slug": "custom",
                                    "name": "Custom",
                                }
                            ]
                        }
                    }
                },
                module_alias=META_ONTOLOGY_ALIAS,
            ).entries
        )

        with pytest.raises(ValueError, match="Unknown parent entity type"):
            load_archimate_4_module(_PACKAGE_DIR, specializations=repo_catalog)
