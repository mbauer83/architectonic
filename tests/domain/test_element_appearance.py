"""How an element is drawn is declared once, by the ontology that owns the vocabulary.

Colour was hardcoded three times — in the PUML generator and twice in the frontend — and the three
disagreed on **every** domain, with one copy missing `implementation` so those elements rendered
grey in the graph explorer while diagrams drew them peach. Corner shape, which says whether a thing
is structure, behaviour or motivation, was expressed nowhere at all.

ArchiMate assigns no formal semantics to colour and defines no hex values, so these are this
product's declaration rather than an approximation of a normative palette. That is precisely why
there must be exactly one of them.
"""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.element_appearance import (
    CORNER_STYLES,
    DeEmphasis,
    ElementAppearance,
)
from src.infrastructure.app_bootstrap import get_module_registry


def _archimate_appearance() -> ElementAppearance:
    modules = get_module_registry().all_ontologies()
    module = next(m for name, m in modules.items() if "archimate" in name)
    return module.element_appearance


class TestTheDeclarationIsRead:
    def test_every_domain_this_ontology_places_elements_in_has_a_colour(self) -> None:
        """A domain with elements and no colour is the gap that put `implementation` into one
        palette and not another. Over the ontology's *own* domains: another module's domains are
        that module's to colour, which is what makes the declaration per-ontology."""
        modules = get_module_registry().all_ontologies()
        module = next(m for name, m in modules.items() if "archimate" in name)
        own_domains = {info.hierarchy[0] for info in module.entity_types.values() if info.hierarchy}

        for domain in sorted(own_domains):
            assert module.element_appearance.color_for(domain), f"no colour declared for {domain!r}"

    @pytest.mark.parametrize(
        "classes,expected",
        [
            (["motivation-element"], "diagonal"),
            (["behavior-element"], "rounded"),
            (["internal-behavior-element"], "rounded"),
            (["strategy-behavior-element"], "rounded"),
            (["active-structure-element"], "square"),
            (["passive-structure-element"], "square"),
            (["composite-element"], "square"),
        ],
    )
    def test_a_class_resolves_to_the_corner_its_category_is_drawn_with(
        self, classes: list[str], expected: str
    ) -> None:
        assert _archimate_appearance().corner_for(classes) == expected

    def test_every_entity_type_resolves_to_a_corner(self) -> None:
        """Including the ones carrying no categorised class: they take the default rather than
        producing no answer, because an element still has to be drawn."""
        modules = get_module_registry().all_ontologies()
        module = next(m for name, m in modules.items() if "archimate" in name)

        for type_name, info in module.entity_types.items():
            assert module.element_appearance.corner_for(info.classes) in CORNER_STYLES, type_name


class TestSilenceIsNotAClaim:
    def test_an_ontology_that_declares_nothing_resolves_to_nothing(self) -> None:
        appearance = ElementAppearance.from_mapping({})

        assert appearance.is_empty
        assert appearance.color_for("motivation") is None

    def test_and_still_answers_a_corner_because_an_element_is_still_drawn(self) -> None:
        assert ElementAppearance.from_mapping({}).corner_for(["motivation-element"]) == "square"

    def test_a_malformed_declaration_is_ignored_rather_than_raising(self) -> None:
        """An ontology that has not yet declared its appearance should render plainly, not fail to
        load — the same tolerance `parse_relation_notation` applies."""
        appearance = ElementAppearance.from_mapping({"element_appearance": "not a mapping"})

        assert appearance.is_empty


class TestDeEmphasisIsDerivedFromTheOneColour:
    def test_a_muted_colour_moves_toward_the_declared_base(self) -> None:
        appearance = ElementAppearance(
            domain_colors={"motivation": "#000000"},
            de_emphasis=DeEmphasis(toward="#FFFFFF", amount=0.5),
        )

        assert appearance.de_emphasized("#000000") == "#808080"

    def test_no_declared_rule_leaves_the_colour_alone(self) -> None:
        """Absent a rule, a surface gets the colour itself rather than a guess at a muted one."""
        appearance = ElementAppearance(domain_colors={"motivation": "#D1BADC"})

        assert appearance.de_emphasized("#D1BADC") == "#D1BADC"

    def test_an_unreadable_colour_is_returned_unchanged(self) -> None:
        appearance = ElementAppearance(de_emphasis=DeEmphasis(toward="#FFFFFF", amount=0.5))

        assert appearance.de_emphasized("not-a-colour") == "not-a-colour"

    def test_the_shipped_rule_lightens_rather_than_darkens(self) -> None:
        """A de-emphasized element must read as *receding*, which is what mixing toward white does
        on this palette. Asserted as a property, not as a hex, so the amount can be tuned."""
        appearance = _archimate_appearance()
        declared = appearance.color_for("motivation")
        assert declared is not None

        muted = appearance.de_emphasized(declared)

        assert muted != declared
        assert int(muted.lstrip("#")[0:2], 16) > int(declared.lstrip("#")[0:2], 16)
