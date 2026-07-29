from __future__ import annotations

from src.domain.ontology_representation.ontology_types import mapping_spec_from_config


def test_mapping_spec_from_config_supports_structured_sources() -> None:
    spec = mapping_spec_from_config(
        {
            "entity_types": ["role"],
            "entity_classes": ["active-structure-element"],
            "sources": [
                {"ontology": "archimate_4", "entity_type": "role", "transparent": True},
                {"ontology": "archimate_4", "entity_class": "active-structure-element"},
            ],
        }
    )

    assert spec.entity_types == ("role",)
    assert spec.entity_classes == ("active-structure-element",)
    assert len(spec.sources) == 2
    assert spec.sources[0].ontology == "archimate_4"
    assert spec.sources[0].entity_type == "role"
    assert spec.sources[0].transparent is True
    assert spec.sources[1].entity_class == "active-structure-element"


def test_mapping_spec_has_any_detects_sources_only() -> None:
    spec = mapping_spec_from_config({"sources": [{"ontology": "archimate_4", "entity_type": "role"}]})

    assert spec.has_any() is True
