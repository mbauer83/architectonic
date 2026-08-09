"""The classification levels a meta-ontology declares, and the rules a declaration must satisfy.

The chain — domain, entity type, specialization — has always existed in the data. What this adds is
its characterisation, and the reason it is worth adding is the third rule below: the two-tier
verification the scratchpad needs (refusal at the level relationships are keyed on, a warning at the
level that only narrows them) becomes a consequence of what the ontology says about itself, rather
than a rule restated in each consumer.

The declaration is optional, and the two modules that omit it are *right* to: the derived default is
their behaviour. That is asserted here too, because an "optional" field that silently changes what
the modules omitting it do would be a migration disguised as a default.
"""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.classification_levels import (
    DERIVED_DEFAULT_LEVELS,
    ClassificationLevel,
    ClassificationLevelsError,
    attribute_level,
    classification_levels_for,
    classification_levels_from_config,
    is_liftable,
    relationship_keying_level,
    validate_classification_levels,
)


def _level(identifier: str, **overrides: object) -> ClassificationLevel:
    defaults: dict[str, object] = {"id": identifier, "label": identifier, "source": "type"}
    return ClassificationLevel(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestTheDefaultIsTodaysBehaviour:
    def test_a_module_declaring_nothing_gets_the_derived_default(self) -> None:
        assert classification_levels_from_config({}) == DERIVED_DEFAULT_LEVELS

    def test_the_default_is_domain_then_type_then_specialization(self) -> None:
        assert [level.id for level in DERIVED_DEFAULT_LEVELS] == ["domain", "entity_type", "specialization"]

    def test_the_default_keys_relationships_on_the_entity_type(self) -> None:
        """Which is what makes a forbidden pair E126 rather than a warning."""
        assert relationship_keying_level(DERIVED_DEFAULT_LEVELS).id == "entity_type"

    def test_the_default_lets_a_specialization_narrow_but_not_key(self) -> None:
        specialization = DERIVED_DEFAULT_LEVELS[-1]

        assert specialization.narrows_relationships
        assert not specialization.keys_relationships

    def test_the_default_is_itself_valid(self) -> None:
        validate_classification_levels(DERIVED_DEFAULT_LEVELS)


class TestReadingADeclaration:
    def test_it_reads_a_declared_block(self) -> None:
        levels = classification_levels_from_config({
            "classification_levels": [
                {"id": "layer", "label": "Layer", "from": "hierarchy", "required": True},
                {"id": "kind", "from": "type", "required": True,
                 "keys_relationships": True, "carries_attributes": True},
            ]
        })

        assert [level.id for level in levels] == ["layer", "kind"]
        assert relationship_keying_level(levels).id == "kind"

    def test_a_missing_label_falls_back_to_the_id(self) -> None:
        levels = classification_levels_from_config({
            "classification_levels": [{"id": "entity_type", "from": "type", "keys_relationships": True,
                                       "carries_attributes": True}]
        })

        assert levels[0].label == "Entity type"

    def test_an_unknown_source_is_refused_with_the_module_named(self) -> None:
        with pytest.raises(ClassificationLevelsError, match="archimate-4-0.*expected hierarchy"):
            classification_levels_from_config(
                {"classification_levels": [{"id": "x", "from": "vibes"}]}, module="archimate-4-0"
            )

    def test_an_empty_block_is_refused_rather_than_read_as_the_default(self) -> None:
        """Declaring nothing and declaring emptiness are different statements."""
        with pytest.raises(ClassificationLevelsError, match="non-empty"):
            classification_levels_from_config({"classification_levels": []})


class TestTheRulesADeclarationMustSatisfy:
    def test_exactly_one_level_keys_relationships(self) -> None:
        with pytest.raises(ClassificationLevelsError, match="exactly one"):
            validate_classification_levels((
                _level("a", keys_relationships=True, carries_attributes=True),
                _level("b", keys_relationships=True),
            ))

    def test_no_keying_level_at_all_is_refused(self) -> None:
        """With none, nothing decides whether a pair is permitted, and the E126/W128 split has no
        anchor — which is the whole reason this declaration exists."""
        with pytest.raises(ClassificationLevelsError, match="exactly one"):
            validate_classification_levels((_level("a", carries_attributes=True),))

    def test_a_level_above_the_keying_one_may_not_narrow_it(self) -> None:
        """It is coarser, so it would be deciding for types it does not distinguish between."""
        with pytest.raises(ClassificationLevelsError, match="above the keying level"):
            validate_classification_levels((
                _level("domain", source="hierarchy", narrows_relationships=True),
                _level("entity_type", keys_relationships=True, carries_attributes=True),
            ))

    def test_duplicate_ids_are_refused(self) -> None:
        with pytest.raises(ClassificationLevelsError, match="duplicate"):
            validate_classification_levels((
                _level("same", keys_relationships=True, carries_attributes=True),
                _level("same"),
            ))

    def test_a_declaration_where_nothing_carries_attributes_is_refused(self) -> None:
        with pytest.raises(ClassificationLevelsError, match="carries attributes"):
            validate_classification_levels((_level("only", keys_relationships=True),))


class TestWhatTheDeclarationAnswers:
    def test_it_says_which_attribute_schema_applies(self) -> None:
        """The deepest reached level that carries one — so a specialization narrows its type's."""
        assert attribute_level(DERIVED_DEFAULT_LEVELS, reached=["domain", "entity_type"]).id == "entity_type"
        assert attribute_level(
            DERIVED_DEFAULT_LEVELS, reached=["domain", "entity_type", "specialization"]
        ).id == "specialization"

    def test_it_says_nothing_applies_before_a_type_is_chosen(self) -> None:
        assert attribute_level(DERIVED_DEFAULT_LEVELS, reached=["domain"]) is None

    def test_it_says_whether_an_element_may_be_lifted_yet(self) -> None:
        """The lift preflight's question: has every required level been reached?"""
        assert not is_liftable(DERIVED_DEFAULT_LEVELS, reached=["domain"])
        assert is_liftable(DERIVED_DEFAULT_LEVELS, reached=["domain", "entity_type"])
        # A specialization is not required, so an unspecialized element is liftable.
        assert is_liftable(DERIVED_DEFAULT_LEVELS, reached=["domain", "entity_type"])


class TestTheDeclarationIsOptional:
    def test_a_module_that_declares_levels_is_asked_for_them(self) -> None:
        class Declaring:
            @property
            def classification_levels(self) -> tuple[ClassificationLevel, ...]:
                return (_level("only", keys_relationships=True, carries_attributes=True),)

        assert [level.id for level in classification_levels_for(Declaring())] == ["only"]

    def test_a_module_that_declares_none_gets_the_default_rather_than_an_error(self) -> None:
        """`sysml_v2_min` and `assurance` say nothing and are right not to: the default is their
        behaviour, so requiring the block would be a migration disguised as a contract."""
        class Silent:
            pass

        assert classification_levels_for(Silent()) == DERIVED_DEFAULT_LEVELS


class TestTheShippedOntologies:
    def test_archimate_declares_its_levels_and_they_validate(self) -> None:
        from src.infrastructure.app_bootstrap import get_module_registry

        registry = get_module_registry()
        archimate = registry.all_ontologies()["archimate-4-0"]
        levels = classification_levels_for(archimate)

        validate_classification_levels(levels, module="archimate-4-0")
        assert [level.id for level in levels] == ["domain", "entity_type", "specialization"]

    def test_every_registered_ontology_answers_with_a_valid_level_list(self) -> None:
        """Including the ones that declare nothing — the point of the default is that they work."""
        from src.infrastructure.app_bootstrap import get_module_registry

        ontologies = get_module_registry().all_ontologies()
        assert ontologies, "no ontology modules registered"
        for name, module in ontologies.items():
            validate_classification_levels(classification_levels_for(module), module=name)
