"""An element whose job is to group others is drawn as an open container, not as a filled box.

ArchiMate draws Grouping with a dashed border and no fill, and for a reason a renderer can act on:
the elements it holds are drawn *inside* it, so a fill would put a coloured plane behind them and a
solid border would read as a boundary of the same kind as the elements it contains.

The notation was already in the generated header, under `<<Grouping>>` — the box an *authored*
grouping gets. The ArchiMate `grouping` **element type** did not get it: it took its domain's fill and
a solid border like any other element, so the same idea was drawn two ways depending on whether a
person had declared the box or the model had.

Declared, not hardcoded. `outline_classes` keys on the classes entity types already carry, exactly as
`corner_classes` does, so the statement reads as one line of intent and a second modelling language
can say the same thing in its own vocabulary. The renderer honours `dashed`; it is told nothing about
groupings.

Nesting was already right — `build_generic_visual_nesting` reads composition and aggregation, so a
grouping drawn with its members nests them. Only the box was wrong.
"""

from __future__ import annotations

from functools import lru_cache

import pytest


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import build_module_registry

    return build_module_registry()


@lru_cache(maxsize=1)
def _archimate():
    for module in _registry().all_ontologies().values():
        if "grouping" in {str(name) for name in module.entity_types}:
            return module
    pytest.skip("no ontology declares a grouping element")
    raise AssertionError


def _appearance():
    return _archimate().element_appearance


def _classes_of(type_name: str) -> tuple[str, ...]:
    info = _archimate().entity_types[type_name]
    return tuple(str(c) for c in info.classes)


class TestTheOntologyDeclaresIt:
    def test_a_grouping_is_declared_an_open_container(self) -> None:
        assert _appearance().outline_for(_classes_of("grouping")) == "dashed"

    def test_the_declaration_is_keyed_on_a_class_rather_than_the_type_name(self) -> None:
        """The `corner_classes` shape. A renderer resolves through classes and never matches on
        `grouping`, so another language can declare its own grouping concept the same way."""
        declared = _appearance().outline_classes.get("dashed", frozenset())

        assert declared, "nothing declares which classes draw as an open container"
        assert "grouping" not in declared, "keyed on the type name rather than on a class"


class TestWhatIsNotAnOpenContainer:
    def test_a_location_is_not(self) -> None:
        """It shares `composite-element` with grouping, and ArchiMate draws it filled. That shared
        class is why the declaration needed one of its own."""
        assert _appearance().outline_for(_classes_of("location")) == "solid"

    @pytest.mark.parametrize("type_name", ["goal", "application-component", "stakeholder", "technology-node"])
    def test_an_ordinary_element_is_not(self, type_name: str) -> None:
        assert _appearance().outline_for(_classes_of(type_name)) == "solid"

    def test_an_element_with_no_classes_falls_back_to_solid(self) -> None:
        assert _appearance().outline_for(()) == "solid"


class TestTheGeneratedIncludeHonoursIt:
    def test_the_grouping_stereotype_is_dashed_and_unfilled(self) -> None:
        from pathlib import Path

        from src.infrastructure.rendering.generate_static_includes import _generate_stereotype_include

        block = _stereotype_block_for(
            _generate_stereotype_include(Path("engagements/ENG-ARCH-REPO/architecture-repository")),
            "grouping",
        )

        assert "BorderStyle dashed" in block, f"the grouping box is not dashed: {block!r}"
        assert "BackgroundColor #FFFFFF" in block, f"the grouping box is filled: {block!r}"

    def test_an_ordinary_element_keeps_its_domain_fill(self) -> None:
        from pathlib import Path

        from src.infrastructure.rendering.generate_static_includes import _generate_stereotype_include

        block = _stereotype_block_for(
            _generate_stereotype_include(Path("engagements/ENG-ARCH-REPO/architecture-repository")),
            "goal",
        )

        assert "BorderStyle dashed" not in block
        assert "BackgroundColor #FFFFFF" not in block


def _stereotype_block_for(include: str, stereotype: str) -> str:
    marker = f"skinparam rectangle<<{stereotype}>> {{"
    assert marker in include, f"no block for <<{stereotype}>>"
    start = include.index(marker)
    return include[start:include.index("}", start) + 1]
