"""The scratchpad refines a note through whatever levels its meta-ontology declares.

Every other suite runs against ArchiMate, or against the default ladder a module gets by declaring
nothing — which is ArchiMate's shape. A scratchpad that hard-coded that shape would pass all of
them. So these register a second meta-ontology whose ladder shares neither the names nor the count
nor the rules: no level above the type, and a level below it that is *required* and is the only one
carrying attributes. Everything asserted is something the declaration says and ArchiMate's does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.application.scratchpad.lift import plan_lift
from src.application.scratchpad.response import to_response
from src.application.scratchpad.verification import (
    classification_levels_of,
    note_verdict_source,
    typing_options,
    verdict_source,
)
from src.domain.ontology_representation.classification_levels import (
    DERIVED_DEFAULT_LEVELS,
    ClassificationLevel,
    classification_levels_from_config,
)
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    SpecializationInfo,
)
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.scratchpad import (
    Note,
    Scratchpad,
    ScratchpadError,
    attribute_level_of,
    may_be_lifted,
    reached_levels,
    scratchpad_from_parts,
)

_NAME = "parts-catalogue"

_LEVELS = classification_levels_from_config({"classification_levels": [
    {"id": "kind", "label": "Kind of part", "from": "type", "required": True,
     "keys_relationships": True},
    {"id": "variant", "label": "Variant", "from": "specializations", "required": True,
     "carries_attributes": True},
]}, module=_NAME)


@dataclass(frozen=True)
class _PartsCatalogue:
    """An ontology module with a two-level ladder: a kind, then a variant that is required."""

    name: str = _NAME

    @property
    def classification_levels(self) -> tuple[ClassificationLevel, ...]:
        return _LEVELS

    @property
    def entity_types(self) -> dict[str, SimpleNamespace]:
        return {"fastener": SimpleNamespace(hierarchy=()), "bearing": SimpleNamespace(hierarchy=())}

    @property
    def connection_types(self) -> dict[str, object]:
        return {}

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def specialization_catalog(self) -> SpecializationCatalog:
        return SpecializationCatalog(tuple(
            SpecializationInfo(
                slug=slug, name=slug, concept_kind="entity", parent_type=parent, module_alias=_NAME
            )
            for slug, parent in (("bolt", "fastener"), ("rivet", "fastener"), ("ball", "bearing"))
        ))

    def entity_types_with_class(self, _cls: str) -> frozenset[str]:
        return frozenset()


class _Registry:
    def all_ontologies(self) -> dict[str, _PartsCatalogue]:
        return {_NAME: _PartsCatalogue()}


@pytest.fixture
def registry() -> _Registry:
    return _Registry()


def _pad(*notes: Note) -> Scratchpad:
    return scratchpad_from_parts(
        artifact_id="SCR@1.a.pad", name="Pad", meta_ontology=_NAME, notes=notes
    )


_KIND, _VARIANT = _LEVELS


class TestTheLadderIsTheDeclaredOne:
    def test_the_scratchpad_reads_its_levels_from_its_own_meta_ontology(self, registry: _Registry) -> None:
        levels = classification_levels_of(registry, _NAME)  # type: ignore[arg-type]

        assert [level.id for level in levels] == ["kind", "variant"]
        assert levels != DERIVED_DEFAULT_LEVELS

    def test_the_read_serves_one_level_per_declared_level_in_declared_order(
        self, registry: _Registry
    ) -> None:
        served = to_response(_pad(), group="g", registry=registry)["classification-levels"]  # type: ignore[arg-type]

        assert [(level["id"], level["label"], level["required"]) for level in served] == [
            ("kind", "Kind of part", True), ("variant", "Variant", True),
        ]
        assert [level["carries-attributes"] for level in served] == [False, True]

    def test_each_level_offers_what_the_level_above_allows(self, registry: _Registry) -> None:
        kind, variant = typing_options(registry, _NAME)  # type: ignore[arg-type]

        assert {option.value: option.within for option in kind.options} == {
            "fastener": "", "bearing": "",
        }
        assert {option.value: option.within for option in variant.options} == {
            "bolt": "fastener", "rivet": "fastener", "ball": "bearing",
        }


class TestTheStepsAreTheDeclaredLevels:
    def test_a_note_is_narrowed_one_declared_level_at_a_time(self) -> None:
        pad = _pad(Note(id="n1", title="A"))

        at_kind = pad.refined("n1", level=_KIND, value="fastener", levels=_LEVELS)
        at_variant = at_kind.refined("n1", level=_VARIANT, value="bolt", levels=_LEVELS)

        assert reached_levels(at_kind.note("n1"), _LEVELS) == ("kind",)
        assert reached_levels(at_variant.note("n1"), _LEVELS) == ("kind", "variant")

    def test_re_answering_a_level_re_opens_the_levels_declared_after_it(self) -> None:
        pad = _pad(Note(id="n1", title="A")).refined(
            "n1", level=_KIND, value="fastener", levels=_LEVELS
        ).refined("n1", level=_VARIANT, value="bolt", levels=_LEVELS)

        again = pad.refined("n1", level=_KIND, value="bearing", levels=_LEVELS)

        assert reached_levels(again.note("n1"), _LEVELS) == ("kind",)

    def test_a_level_the_meta_ontology_does_not_declare_is_refused(self) -> None:
        """ArchiMate's first level is not one of this ontology's, so it is not a step here."""
        pad = _pad(Note(id="n1", title="A"))

        with pytest.raises(ScratchpadError, match="not a classification level of this scratchpad"):
            pad.refined("n1", level=DERIVED_DEFAULT_LEVELS[0], value="motivation", levels=_LEVELS)


class TestLiftabilityIsTheDeclaredRule:
    def _plan(self, registry: _Registry, pad: Scratchpad):  # noqa: ANN202 — the plan's own type
        return plan_lift(
            pad, selection=["n1"], targets={},
            verdict_of=verdict_source(registry, pad),  # type: ignore[arg-type]
            note_verdict_of=note_verdict_source(registry, pad),  # type: ignore[arg-type]
            levels=classification_levels_of(registry, _NAME),  # type: ignore[arg-type]
        )

    def test_a_typed_note_is_not_liftable_while_a_required_level_below_the_type_is_open(
        self, registry: _Registry
    ) -> None:
        """Under the default ladder a type is enough. Here the declaration requires the variant."""
        typed = Note(id="n1", title="A", destination="element", element_type="fastener")

        assert may_be_lifted(typed, DERIVED_DEFAULT_LEVELS)
        assert not may_be_lifted(typed, _LEVELS)

        refused = self._plan(registry, _pad(typed)).of("refuse")
        assert [item.id for item in refused] == ["n1"]
        assert "choose its variant" in refused[0].reason

    def test_it_is_liftable_once_every_required_level_is_reached(self, registry: _Registry) -> None:
        complete = Note(
            id="n1", title="A", destination="element", element_type="fastener", specialization="bolt"
        )

        created = self._plan(registry, _pad(complete)).of("create")

        assert [(item.artifact_type, item.specializations) for item in created] == [
            ("fastener", ("bolt",))
        ]

    def test_the_refusal_names_the_level_as_the_meta_ontology_names_it(
        self, registry: _Registry
    ) -> None:
        undecided = Note(id="n1", title="A", destination="element")

        assert "choose its variant" in self._plan(registry, _pad(undecided)).of("refuse")[0].reason


class TestAttributesAttachWhereTheDeclarationSays:
    def test_a_note_at_the_type_is_below_the_level_that_carries_attributes(self) -> None:
        typed = Note(id="n1", title="A", destination="element", element_type="fastener")

        assert attribute_level_of(typed, DERIVED_DEFAULT_LEVELS) is not None
        assert attribute_level_of(typed, _LEVELS) is None

    def test_it_reaches_that_level_with_the_variant(self) -> None:
        complete = Note(
            id="n1", title="A", destination="element", element_type="fastener", specialization="bolt"
        )

        level = attribute_level_of(complete, _LEVELS)

        assert level is not None and level.id == "variant"
