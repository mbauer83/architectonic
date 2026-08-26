"""An ad-hoc reading of a diagram: what it changes, and what it must never change.

The reader's own architectural decision about this feature is that a lens is *momentary* — it lasts as
long as a visit to the diagram's page and is never written back. So the properties worth gating are
mostly negative, and the sharpest one is the first: the diagram's own body is not touched.

The rest are the ones a shortcut would break:

* **Which colouring applies is the model's answer, not the values'.** An attribute declaring a bounded
  set with no order takes one colour per member; anything else takes a ramp. Deciding from the values
  present on *this* diagram would make one attribute two different pictures on two diagrams.
* **A ramp over an ordinal reads its declared range**, not the drawn extremes — the property
  `viewpoint_scale_styling` already owns, asserted here because the lens is a second caller of it and
  a lens that computed its own bounds would silently lose it.
* **Every element still declares its alias.** The lens rewrites declaration lines, so the round trip
  the register demands is stated at this layer too: same aliases, same order.
* **An element with no value keeps its authored appearance.** Painting it neutral grey would say "this
  is low", which is a claim the model does not make.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.puml_alias_declarations import declared_aliases
from src.application.viewpoints.diagram_reading_lens import ReadingLens, apply_reading_lens
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot

_BODY = """@startuml lens-fixture
skinparam linetype ortho
rectangle "Capabilities" as GRP_1 {
rectangle "Alpha" <<capability>> as CAP_a
rectangle "Beta" <<capability>> as CAP_b
rectangle "Gamma" <<capability>> as CAP_c
}
' Connections
CAP_a -up-> CAP_b
@enduml
"""


class _NoReads:
    """The lens colours by an attribute, so it never follows a connection."""

    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_connection(self, artifact_id: str) -> None:
        return None

    def find_connections_for(self, entity_id: str, **kwargs: object) -> list:
        return []


def _entity(alias: str, **attributes: object) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{alias}",
        artifact_type="capability",
        name=alias,
        version="0.1.0",
        status="active",
        domain="business",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=alias,
        display_alias=alias,
        specializations=(),
        attributes=dict(attributes),
    )


def _registries(
    *, types: dict[str, str] | None = None, enums: dict[str, tuple[str, ...]] | None = None
) -> RegistrySnapshot:
    return RegistrySnapshot(
        known_entity_types=frozenset({"capability"}),
        known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(),
        entity_attribute_types=types or {},
        connection_attribute_types={},
        entity_attribute_enums=enums or {},
        connection_attribute_enums={},
        symmetric_connection_types=frozenset(),
    )


def _apply(entities: list[EntityRecord], lens: ReadingLens, registries: RegistrySnapshot):
    return apply_reading_lens(
        _BODY, entities, lens=lens, read_access=_NoReads(), registries=registries  # type: ignore[arg-type]
    )


_RAMPED = _registries(types={"risk_score": "integer"})
_MEMBERS = ("planned", "active", "retired")
_KEYED = _registries(types={"lifecycle": "string"}, enums={"lifecycle": _MEMBERS})


class TestItIsAReading:
    def test_an_empty_lens_returns_the_body_it_was_given(self) -> None:
        """Not an equal body — the same one. A lens nobody asked for must not even reformat."""
        lensed = _apply([_entity("CAP_a")], ReadingLens(), _RAMPED)

        assert lensed.puml_body == _BODY

    def test_the_lens_never_changes_a_line_it_was_not_asked_about(self) -> None:
        entities = [_entity("CAP_a", risk_score=1)]

        lensed = _apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED)

        untouched = [line for line in lensed.puml_body.splitlines() if "CAP_a" not in line]
        assert untouched == [line for line in _BODY.splitlines() if "CAP_a" not in line]

    def test_every_element_still_declares_its_alias(self) -> None:
        """The round trip the syntax register demands, at the layer that rewrites whole bodies."""
        entities = [_entity(alias, risk_score=n) for n, alias in enumerate(("CAP_a", "CAP_b", "CAP_c"))]
        before = [(d.alias, d.opens_block) for d in declared_aliases(_BODY)]

        lensed = _apply(entities, ReadingLens(colour_by="risk_score", printed=("risk_score",)), _RAMPED)

        assert [(d.alias, d.opens_block) for d in declared_aliases(lensed.puml_body)] == before


class TestWhichColouringApplies:
    def test_an_unordered_value_set_takes_one_colour_per_member(self) -> None:
        entities = [_entity("CAP_a", lifecycle="planned"), _entity("CAP_b", lifecycle="retired")]

        lensed = _apply(entities, ReadingLens(colour_by="lifecycle"), _KEYED)

        assert [key.member for key in lensed.color_keys] == list(_MEMBERS)
        assert lensed.coloured == 2

    def test_the_member_colours_are_all_different(self) -> None:
        lensed = _apply([_entity("CAP_a", lifecycle="planned")], ReadingLens(colour_by="lifecycle"), _KEYED)

        colours = [key.color for key in lensed.color_keys]
        assert len(set(colours)) == len(colours)

    def test_a_member_keeps_its_colour_however_few_are_drawn(self) -> None:
        """The assignment follows the *declared* order, so a diagram drawing only `retired` paints it
        the same colour as a diagram drawing all three. Reading from the drawn values instead would
        make one attribute two pictures, and a reader could not carry a reading between them."""
        whole = _apply([_entity("CAP_a", lifecycle="planned")], ReadingLens(colour_by="lifecycle"), _KEYED)
        one = _apply([_entity("CAP_a", lifecycle="retired")], ReadingLens(colour_by="lifecycle"), _KEYED)

        assert {k.member: k.color for k in whole.color_keys} == {k.member: k.color for k in one.color_keys}

    def test_a_number_takes_a_ramp_and_reports_its_legend(self) -> None:
        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        lensed = _apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED)

        assert lensed.color_keys == ()
        assert [(legend.minimum, legend.maximum) for legend in lensed.legends] == [(2.0, 8.0)]

    def test_an_ordinal_ramps_over_its_declared_range_not_the_drawn_one(self) -> None:
        """Declared as an ordinal, so its enum *is* the scale. Both drawn entities sit at the mild end;
        drawn-extreme bounds would paint the milder of them as the lowest and the other as the worst."""
        registries = _registries(
            types={"severity": "ordinal"}, enums={"severity": ("negligible", "minor", "major", "critical")}
        )
        entities = [_entity("CAP_a", severity="negligible"), _entity("CAP_b", severity="minor")]

        lensed = _apply(entities, ReadingLens(colour_by="severity"), registries)

        assert [(legend.minimum, legend.maximum) for legend in lensed.legends] == [(0.0, 3.0)]
        assert [legend.maximum_label for legend in lensed.legends] == ["critical"]


class TestWhatIsLeftAlone:
    def test_an_element_with_no_value_is_not_coloured(self) -> None:
        """Neutral grey would read as "low", which the model does not say."""
        entities = [_entity("CAP_a", risk_score=4), _entity("CAP_b")]

        lensed = _apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED)

        assert lensed.coloured == 1
        assert lensed.unstyled == 1

    def test_an_element_the_diagram_draws_but_the_model_does_not_place_is_untouched(self) -> None:
        lensed = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(colour_by="risk_score"), _RAMPED)

        assert 'rectangle "Beta" <<capability>> as CAP_b' in lensed.puml_body

    def test_an_attribute_nothing_carries_is_named_rather_than_counted(self) -> None:
        lensed = _apply([_entity("CAP_a")], ReadingLens(printed=("risk_score", "owner")), _RAMPED)

        assert lensed.silent == ("risk_score", "owner")
        assert lensed.printed_on == 0

    def test_an_attribute_no_type_declares_is_reported_rather_than_silently_ignored(self) -> None:
        """A reader who chose an attribute and got the plain picture back cannot tell a lens that found
        nothing from a lens that never ran."""
        lensed = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(colour_by="not_an_attribute"), _RAMPED)

        assert lensed.coloured == 0
        assert lensed.notes and "not_an_attribute" in lensed.notes[0]


class TestWhatIsPrinted:
    def test_a_value_is_appended_to_the_element_label(self) -> None:
        lensed = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(printed=("risk_score",)), _RAMPED)

        assert "risk_score: 4" in lensed.puml_body
        assert lensed.printed_on == 1

    def test_only_the_asked_for_attributes_are_printed(self) -> None:
        entities = [_entity("CAP_a", risk_score=4, owner="platform")]

        lensed = _apply(entities, ReadingLens(printed=("risk_score",)), _RAMPED)

        assert "owner" not in lensed.puml_body

    @pytest.mark.parametrize("value", ["", None])
    def test_an_empty_value_prints_nothing(self, value: object) -> None:
        """A column of `owner: —` spends the diagram's room saying nothing."""
        lensed = _apply([_entity("CAP_a", owner=value)], ReadingLens(printed=("owner",)), _RAMPED)

        assert "owner" not in lensed.puml_body
