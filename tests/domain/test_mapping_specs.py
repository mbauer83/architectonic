from __future__ import annotations

from src.domain.ontology_representation.ontology_types import (
    MappingSourceSpec,
    PermittedMappingSpec,
    mapping_spec_from_config,
)


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


def test_as_config_round_trips_through_the_parser() -> None:
    """The projection and the parser are two directions of one representation.

    Five call sites had spelled the serialised form by hand — four diagram-type modules and the write
    boundary's guidance serialiser — so a field added to the dataclass reached the wire from none of
    them. Holding the pair as a round trip is what makes the projection the single statement of that
    form rather than a sixth copy.
    """
    spec = PermittedMappingSpec(
        entity_types=("role", "business-actor"),
        entity_classes=("active-structure-element",),
        sources=(
            MappingSourceSpec(ontology="archimate_4", entity_type="role", transparent=True),
            MappingSourceSpec(ontology="archimate_4", entity_class="active-structure-element"),
        ),
    )

    assert mapping_spec_from_config(spec.as_config()) == spec


def test_as_config_omits_sources_it_does_not_have() -> None:
    # The key's absence is what a spec with no ontology sources has always looked like on the wire;
    # an empty list would change the payload of every diagram type declaring plain types and classes.
    spec = PermittedMappingSpec(entity_types=("role",))

    assert "sources" not in spec.as_config()
    assert mapping_spec_from_config(spec.as_config()) == spec


def test_a_source_naming_neither_type_nor_class_round_trips_as_nulls() -> None:
    # Both fields are nullable and both spellings must survive: the parser reads a falsy value as
    # `None`, so a projection emitting `""` would round-trip to a different spec.
    spec = PermittedMappingSpec(sources=(MappingSourceSpec(ontology="gsn"),))

    assert spec.as_config()["sources"] == [
        {"ontology": "gsn", "entity_type": None, "entity_class": None, "transparent": False}
    ]
    assert mapping_spec_from_config(spec.as_config()) == spec
