"""An ad-hoc reading of a diagram: what it changes, and what it must never change.

The reader's own architectural decision about this feature is that a lens is *momentary* — it lasts as
long as a visit to the diagram's page and is never written back. So the properties worth gating are
mostly negative, and the sharpest one is the first: the diagram's own body is not touched.

The rest are the ones a shortcut would break:

* **Which colouring applies is the model's answer, not the values'.** An attribute declaring a bounded
  set with no order takes one colour per member; anything else takes a ramp. Deciding from the values
  present on *this* diagram would make one attribute two different pictures on two diagrams.

**Asserted over the emitted body**, because that is what the function returns and what the renderer
receives. It used to return a record carrying counts, legends and notes, and the assertions read those
— seven fields of which the route used one. Reading the body instead is both the product's own path and
the round trip this project asks of a syntax it writes: the fills are found with the same
`declared_aliases` the verifier reads a diagram with.
* **A ramp over an ordinal reads its declared range**, not the drawn extremes — the property
  `viewpoint_scale_styling` already owns, asserted here because the lens is a second caller of it and
  a lens that computed its own bounds would silently lose it.
* **Every element still declares its alias.** The lens rewrites declaration lines, so the round trip
  the register demands is stated at this layer too: same aliases, same order.
* **An element with no value keeps its authored appearance.** Painting it neutral grey would say "this
  is low", which is a claim the model does not make.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.puml_alias_declarations import alias_declared_on, declared_aliases
from src.application.viewpoints.diagram_reading_lens import ReadingLens, apply_reading_lens
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_style_values import AD_HOC_RAMP_TOKENS, STYLE_TOKEN_COLORS

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


def _apply(
    entities: list[EntityRecord],
    lens: ReadingLens,
    registries: RegistrySnapshot,
    palette: tuple[str, ...] = (),
) -> str:
    """*palette* is the member list a palette colouring assigns from, empty for a ramp.

    Passed in rather than looked up, which is the point: which of the two colourings applies is
    decided once, upstream, off the same offers the reader's controls were built from. The lens used
    to ask the criteria snapshot itself, and the two readings differed on a boolean.
    """
    return apply_reading_lens(
        _BODY, entities, lens=lens, read_access=_NoReads(),  # type: ignore[arg-type]
        registries=registries, palette=palette,
    )


def _fills(body: str) -> dict[str, str]:
    """The fill each alias was given, read back out of the body. Empty for an element left alone."""
    found: dict[str, str] = {}
    for line in body.splitlines():
        declaration = alias_declared_on(line)
        match = re.search(r"#back:([0-9a-fA-F]{6})", line)
        if declaration is not None and match is not None:
            found[declaration.alias] = f"#{match.group(1).lower()}"
    return found


_RAMPED = _registries(types={"risk_score": "integer"})
_MEMBERS = ("planned", "active", "retired")
_KEYED = _registries(types={"lifecycle": "string"}, enums={"lifecycle": _MEMBERS})


class TestItIsAReading:
    def test_an_empty_lens_returns_the_body_it_was_given(self) -> None:
        """Not an equal body — the same one. A lens nobody asked for must not even reformat."""
        assert _apply([_entity("CAP_a")], ReadingLens(), _RAMPED) == _BODY

    def test_the_lens_never_changes_a_line_it_was_not_asked_about(self) -> None:
        entities = [_entity("CAP_a", risk_score=1)]

        body = _apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED)

        untouched = [line for line in body.splitlines() if "CAP_a" not in line]
        assert untouched == [line for line in _BODY.splitlines() if "CAP_a" not in line]

    def test_every_element_still_declares_its_alias(self) -> None:
        """The round trip the syntax register demands, at the layer that rewrites whole bodies."""
        entities = [_entity(alias, risk_score=n) for n, alias in enumerate(("CAP_a", "CAP_b", "CAP_c"))]
        before = [(d.alias, d.opens_block) for d in declared_aliases(_BODY)]

        body = _apply(entities, ReadingLens(colour_by="risk_score", printed=("risk_score",)), _RAMPED)

        assert [(d.alias, d.opens_block) for d in declared_aliases(body)] == before


class TestWhichColouringApplies:
    def test_an_unordered_value_set_gives_each_member_its_own_colour(self) -> None:
        entities = [_entity("CAP_a", lifecycle="planned"), _entity("CAP_b", lifecycle="retired")]

        fills = _fills(_apply(entities, ReadingLens(colour_by="lifecycle"), _KEYED, _MEMBERS))

        assert set(fills) == {"CAP_a", "CAP_b"}
        assert fills["CAP_a"] != fills["CAP_b"]

    def test_a_member_keeps_its_colour_however_few_are_drawn(self) -> None:
        """The assignment follows the *declared* order, so a diagram drawing only `retired` paints it
        the same colour as a diagram drawing all three. Reading from the drawn values instead would
        make one attribute two pictures, and a reader could not carry a reading between them."""
        together = _fills(
            _apply(
                [_entity("CAP_a", lifecycle="planned"), _entity("CAP_b", lifecycle="retired")],
                ReadingLens(colour_by="lifecycle"),
                _KEYED,
                _MEMBERS,
            )
        )
        alone = _fills(
            _apply(
                [_entity("CAP_b", lifecycle="retired")],
                ReadingLens(colour_by="lifecycle"),
                _KEYED,
                _MEMBERS,
            )
        )

        assert alone["CAP_b"] == together["CAP_b"]

    def test_a_number_ramps_between_the_drawn_extremes(self) -> None:
        """A number has no declared range, so the drawn extremes are the only honest bounds — and the
        two ends must land on the endpoints rather than somewhere inside the gradient."""
        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        fills = _fills(_apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED))

        assert fills["CAP_a"] == STYLE_TOKEN_COLORS[AD_HOC_RAMP_TOKENS[0]]
        assert fills["CAP_b"] == STYLE_TOKEN_COLORS[AD_HOC_RAMP_TOKENS[1]]

    def test_an_ordinal_ramps_over_its_declared_range_not_the_drawn_one(self) -> None:
        """Declared as an ordinal, so its enum *is* the scale. Both drawn entities sit at the mild end,
        so neither may reach the far endpoint; drawn-extreme bounds would paint the milder of them as
        the lowest and the other as the worst."""
        registries = _registries(
            types={"severity": "ordinal"}, enums={"severity": ("negligible", "minor", "major", "critical")}
        )
        entities = [_entity("CAP_a", severity="negligible"), _entity("CAP_b", severity="minor")]

        fills = _fills(_apply(entities, ReadingLens(colour_by="severity"), registries))

        assert fills["CAP_a"] == STYLE_TOKEN_COLORS[AD_HOC_RAMP_TOKENS[0]]
        assert fills["CAP_b"] != STYLE_TOKEN_COLORS[AD_HOC_RAMP_TOKENS[1]]

    def test_a_reader_s_own_gradient_replaces_the_declared_endpoints(self) -> None:
        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        fills = _fills(
            _apply(entities, ReadingLens(colour_by="risk_score", ramp=("#000000", "#ffffff")), _RAMPED)
        )

        assert (fills["CAP_a"], fills["CAP_b"]) == ("#000000", "#ffffff")

    def test_a_reader_s_own_member_colour_replaces_just_that_member(self) -> None:
        entities = [_entity("CAP_a", lifecycle="planned"), _entity("CAP_b", lifecycle="retired")]
        plain = _fills(_apply(entities, ReadingLens(colour_by="lifecycle"), _KEYED, _MEMBERS))

        fills = _fills(_apply(
            entities, ReadingLens(colour_by="lifecycle", key={"planned": "#123456"}), _KEYED, _MEMBERS
        ))

        assert fills["CAP_a"] == "#123456"
        assert fills["CAP_b"] == plain["CAP_b"]


class TestWhatIsLeftAlone:
    def test_an_element_with_no_value_is_not_coloured(self) -> None:
        """Neutral grey would read as "low", which the model does not say."""
        entities = [_entity("CAP_a", risk_score=4), _entity("CAP_b")]

        fills = _fills(_apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED))

        assert set(fills) == {"CAP_a"}

    def test_an_element_the_diagram_draws_but_the_model_does_not_place_is_untouched(self) -> None:
        body = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(colour_by="risk_score"), _RAMPED)

        assert 'rectangle "Beta" <<capability>> as CAP_b' in body

    def test_an_attribute_nothing_carries_prints_nothing(self) -> None:
        """And says so nowhere in the body. The panel is where a reader learns an attribute is empty,
        from the presence count it already shows — a note threaded back through here had no reader."""
        body = _apply([_entity("CAP_a")], ReadingLens(printed=("risk_score", "owner")), _RAMPED)

        assert body == _BODY

    def test_an_attribute_no_type_declares_colours_nothing(self) -> None:
        """Rather than reading a raw value straight off the record. The schema-drift contract the
        styling already keeps: an attribute path the registries do not know is treated as absent."""
        body = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(colour_by="not_an_attribute"), _RAMPED)

        assert _fills(body) == {}


class TestWhatIsPrinted:
    def test_a_value_is_appended_to_the_element_label(self) -> None:
        body = _apply([_entity("CAP_a", risk_score=4)], ReadingLens(printed=("risk_score",)), _RAMPED)

        assert "risk_score: 4" in body

    def test_only_the_asked_for_attributes_are_printed(self) -> None:
        entities = [_entity("CAP_a", risk_score=4, owner="platform")]

        assert "owner" not in _apply(entities, ReadingLens(printed=("risk_score",)), _RAMPED)

    @pytest.mark.parametrize("value", ["", None])
    def test_an_empty_value_prints_nothing(self, value: object) -> None:
        """A column of `owner: —` spends the diagram's room saying nothing."""
        assert "owner" not in _apply([_entity("CAP_a", owner=value)], ReadingLens(printed=("owner",)), _RAMPED)


class TestAGradientOnARamp:
    """A named gradient reaches a ramp only when a reader names one.

    The gradients run bad to good. A number a reader colours by is as often a risk score, where high
    is the bad end, so defaulting a ramp to one would paint a large risk green — the opposite of what
    the model says. The reader who wants a scale's own direction picks the gradient that runs that
    way, which is why each is offered reversed.
    """

    def test_a_number_keeps_the_magnitude_pair_when_no_gradient_is_named(self) -> None:
        from src.domain.viewpoints.viewpoint_style_values import AD_HOC_RAMP_TOKENS, STYLE_TOKEN_COLORS

        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        fills = _fills(_apply(entities, ReadingLens(colour_by="risk_score"), _RAMPED))

        assert fills["CAP_a"] == STYLE_TOKEN_COLORS[AD_HOC_RAMP_TOKENS[0]]

    def test_a_named_gradient_runs_the_ramp(self) -> None:
        from src.domain.viewpoints.viewpoint_style_values import ATTRIBUTE_GRADIENTS

        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        fills = _fills(_apply(
            entities, ReadingLens(colour_by="risk_score", gradient="green-red"), _RAMPED
        ))

        assert fills["CAP_a"] == ATTRIBUTE_GRADIENTS["green-red"][0]
        assert fills["CAP_b"] == ATTRIBUTE_GRADIENTS["green-red"][-1]

    def test_the_reverse_puts_the_high_end_where_the_reader_asked(self) -> None:
        """The whole point: a risk score coloured `green-red` reads high as red."""
        entities = [_entity("CAP_a", risk_score=2), _entity("CAP_b", risk_score=8)]

        forwards = _fills(_apply(
            entities, ReadingLens(colour_by="risk_score", gradient="red-green"), _RAMPED))
        backwards = _fills(_apply(
            entities, ReadingLens(colour_by="risk_score", gradient="green-red"), _RAMPED))

        assert forwards["CAP_a"] == backwards["CAP_b"]
        assert forwards["CAP_b"] == backwards["CAP_a"]
