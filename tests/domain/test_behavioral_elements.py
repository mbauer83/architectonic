"""Which entity types act, resolved from an ontology's four short lists.

The lists exist instead of a boolean per entity type because four names read as one statement of
intent — "these classes act, except these, plus these types, minus these" — where forty booleans are
the same information scattered across a file.

The two subtractive lists are not symmetry for its own sake. ArchiMate's taxonomy is coarser than the
question in one specific place, and these tests pin it: capability, course-of-action and value-stream
all declare `behavior-element` alongside `strategy-behavior-element`, so a plain allowlist admits
them — and a capability does not malfunction, it is held or missing. That single gap was 17 of the 107
findings that taught readers to ignore the panel.
"""

from __future__ import annotations

from src.domain.ontology_representation.behavioral_elements import (
    BehavioralElementDeclaration,
    resolve_behavioral_types,
)

#: A miniature of the real taxonomy, including the overlap that makes the exclusion necessary.
CLASSES = {
    "application-component": ["active-structure-element", "internal-active-structure-element"],
    "service": ["behavior-element"],
    "process": ["behavior-element", "internal-behavior-element"],
    "capability": ["behavior-element", "strategy-behavior-element"],
    "value-stream": ["behavior-element", "strategy-behavior-element"],
    "goal": ["motivation-element"],
    "data-object": ["passive-structure-element"],
}

ACTS = BehavioralElementDeclaration(
    classes=frozenset({"active-structure-element", "behavior-element"}),
    excluded_classes=frozenset({"strategy-behavior-element"}),
)


class TestResolution:
    def test_a_type_carrying_a_listed_class_acts(self) -> None:
        resolved = resolve_behavioral_types(CLASSES, ACTS)

        assert {"application-component", "service", "process"} <= resolved

    def test_a_strategy_behaviour_element_does_not_act(self) -> None:
        """It declares `behavior-element` too, so the allowlist alone admits it. A capability is held
        or missing; it does not malfunction."""
        resolved = resolve_behavioral_types(CLASSES, ACTS)

        assert "capability" not in resolved
        assert "value-stream" not in resolved

    def test_motivation_and_passive_structure_do_not_act(self) -> None:
        resolved = resolve_behavioral_types(CLASSES, ACTS)

        assert "goal" not in resolved
        assert "data-object" not in resolved

    def test_an_exclusion_beats_the_class_that_would_have_admitted_it(self) -> None:
        declaration = BehavioralElementDeclaration(
            classes=frozenset({"behavior-element"}),
            excluded_classes=frozenset({"strategy-behavior-element"}),
        )

        assert "capability" not in resolve_behavioral_types(CLASSES, declaration)


class TestTheAdditiveAndSubtractiveTypeLists:
    def test_a_named_type_acts_even_with_no_matching_class(self) -> None:
        declaration = BehavioralElementDeclaration(
            classes=frozenset({"behavior-element"}),
            types=frozenset({"data-object"}),
        )

        assert "data-object" in resolve_behavioral_types(CLASSES, declaration)

    def test_a_named_type_that_does_not_exist_is_ignored(self) -> None:
        """A declaration cannot invent a type, so a stale name is silent rather than a phantom entry."""
        declaration = BehavioralElementDeclaration(
            classes=frozenset({"behavior-element"}),
            types=frozenset({"not-a-type"}),
        )

        assert "not-a-type" not in resolve_behavioral_types(CLASSES, declaration)

    def test_an_excluded_type_is_removed_despite_its_class(self) -> None:
        declaration = BehavioralElementDeclaration(
            classes=frozenset({"behavior-element"}),
            excluded_types=frozenset({"service"}),
        )

        resolved = resolve_behavioral_types(CLASSES, declaration)
        assert "service" not in resolved
        assert "process" in resolved

    def test_an_explicit_exclusion_outranks_an_explicit_inclusion(self) -> None:
        """Between two explicit statements, honour the one that removes a claim: a type wrongly
        omitted costs a missing finding, one wrongly admitted costs a question with no answer."""
        declaration = BehavioralElementDeclaration(
            classes=frozenset(),
            types=frozenset({"goal"}),
            excluded_types=frozenset({"goal"}),
        )

        assert "goal" not in resolve_behavioral_types(CLASSES, declaration)


class TestAnUndeclaredOntologySaysNothing:
    def test_an_empty_declaration_resolves_to_nothing(self) -> None:
        """Silence is not a claim that everything acts, nor that nothing does. A caller that needs
        the answer gets none, and says so, rather than guessing."""
        assert resolve_behavioral_types(CLASSES, BehavioralElementDeclaration()) == frozenset()

    def test_exclusions_alone_resolve_to_nothing(self) -> None:
        declaration = BehavioralElementDeclaration(
            excluded_classes=frozenset({"strategy-behavior-element"}),
        )

        assert resolve_behavioral_types(CLASSES, declaration) == frozenset()


class TestReadingADeclaration:
    def test_all_four_lists_are_read(self) -> None:
        declaration = BehavioralElementDeclaration.from_mapping({
            "behavioral_element_classes": ["behavior-element"],
            "non_behavioral_element_classes": ["strategy-behavior-element"],
            "behavioral_element_types": ["data-object"],
            "non_behavioral_element_types": ["service"],
        })

        assert declaration.classes == frozenset({"behavior-element"})
        assert declaration.excluded_classes == frozenset({"strategy-behavior-element"})
        assert declaration.types == frozenset({"data-object"})
        assert declaration.excluded_types == frozenset({"service"})

    def test_absent_keys_mean_empty(self) -> None:
        assert BehavioralElementDeclaration.from_mapping({}).is_empty

    def test_a_non_list_value_is_ignored_rather_than_crashing_the_load(self) -> None:
        """An ontology is configuration an operator edits; one malformed key must not take the
        whole registry down at startup."""
        declaration = BehavioralElementDeclaration.from_mapping(
            {"behavioral_element_classes": "behavior-element"},
        )

        assert declaration.classes == frozenset()


class TestTheArchimateOntologyDeclaresIt:
    """Against the real ontology, because the lists are only right if they resolve to the right set.

    The unit tests above use a miniature taxonomy; these pin the answer the product actually gets.
    """

    def _resolved(self) -> frozenset[str]:
        from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

        return build_runtime_catalogs(get_module_registry()).ontology.behavioral_entity_types()

    def test_the_things_an_fmea_is_about_are_included(self) -> None:
        expected = {
            "application-component", "service", "function", "process", "technology-node",
            "device", "system-software", "communication-network", "distribution-network",
            "facility", "equipment",
        }

        assert expected <= self._resolved()

    def test_intent_is_excluded(self) -> None:
        """A goal is met or missed; a requirement is satisfied or not. Neither malfunctions, and
        asking for their failure modes is a question with no answer."""
        for type_name in ("goal", "outcome", "requirement", "principle", "value", "driver"):
            assert type_name not in self._resolved(), type_name

    def test_strategy_behaviour_is_excluded(self) -> None:
        """The reason `non_behavioral_element_classes` exists: these declare `behavior-element` too."""
        for type_name in ("capability", "value-stream", "course-of-action"):
            assert type_name not in self._resolved(), type_name

    def test_passive_structure_is_excluded(self) -> None:
        """A data object does not malfunction; it is affected by whatever acts on it, which is where
        the failure actually lives."""
        for type_name in ("data-object", "business-object", "artifact", "material"):
            assert type_name not in self._resolved(), type_name

    def test_the_assurance_ontology_contributes_nothing(self) -> None:
        """Assurance node types are not architecture elements; a hazard is not a thing that acts."""
        for type_name in ("hazard", "loss", "failure-mode", "assurance-constraint"):
            assert type_name not in self._resolved(), type_name
