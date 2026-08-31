"""What a legend says, read out of the body's own preamble rather than from today's ontology.

That distinction is the point of this file. A body may carry the generated declarations *inlined*, and
an inlined copy is what PlantUML is actually handed — so a legend derived from the ontology would
describe a palette the diagram is not using. This repository has had nine such diagrams at once, all
drawing colours their bodies were authored with. Reading the preamble makes a legend describe the
picture that was drawn.

The other half is that only *referenced* declarations count. `ArchimateDeclarations` holds the whole
catalogue; a body uses a handful of it, and the handful is what a reader needs explained.

**Styling a stereotype is not drawing one**, and the two are spelled with the same `<<name>>`. Since
every stored body carries its own skinparam blocks inlined, reading the glyph anywhere reported each
kind a body styles as a kind it draws — which the legend turned into a row for a fill no element on the
picture carried.
"""

from __future__ import annotations

from src.application.puml_alias_declarations import overrides_colour
from src.domain.ontology_representation.relation_notation import RelationNotation
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.archimate_legend import (
    arrow_rows,
    colour_rows,
    glyph_rows,
    notations_referenced_in,
    readable_label,
    shape_rows,
)

_STEREOTYPES = """\
skinparam rectangle<<capability>> {
  BackgroundColor #EFBD5D
  BorderColor #48391C
  RoundCorner 14
}
skinparam rectangle<<resource>> {
  BackgroundColor #EFBD5D
  BorderColor #48391C
}
skinparam rectangle<<driver>> {
  BackgroundColor #D1BADC
  BorderColor #3F3842
  DiagonalCorner 10
}
skinparam rectangle<<Grouping>> {
  BackgroundColor #FFFFFF
  BorderColor #9E9E9E
  BorderStyle dashed
}
"""

_GLYPHS = 'sprite $archimate_capability <svg/>\nsprite $archimate_driver <svg/>\n'
_RELATIONS = "!define Rel_Realization(from, to, label) from ..|> to\n"


def _declarations() -> ArchimateDeclarations:
    return ArchimateDeclarations.from_includes(
        stereotypes=_STEREOTYPES, glyphs=_GLYPHS, relations=_RELATIONS
    )


_BODY = """\
@startuml x
rectangle "A" <<capability>> as A
rectangle "B" <<resource>> as B
rectangle "<$archimate_capability{scale=1.2}> A" <<capability>> as C
@enduml
"""


class TestWhatTheBodyDeclares:
    def test_a_stereotype_block_says_the_fill_and_the_corner(self) -> None:
        notation = _declarations().notation_of("capability")

        assert notation is not None
        assert (notation.fill, notation.corner) == ("#EFBD5D", "rounded")

    def test_no_corner_declaration_means_square(self) -> None:
        """Silence is the absence of a claim, which is the same reading `ElementAppearance` gives it."""
        notation = _declarations().notation_of("resource")

        assert notation is not None
        assert notation.corner == "square"

    def test_a_diagonal_corner_is_its_own_shape(self) -> None:
        notation = _declarations().notation_of("driver")

        assert notation is not None
        assert notation.corner == "diagonal"

    def test_a_dashed_border_is_reported(self) -> None:
        notation = _declarations().notation_of("Grouping")

        assert notation is not None
        assert notation.dashed is True

    def test_a_stereotype_nothing_declares_has_no_notation(self) -> None:
        assert _declarations().notation_of("not-a-stereotype") is None


class TestOnlyWhatIsReferenced:
    def test_only_the_stereotypes_the_body_uses_are_described(self) -> None:
        """`driver` is declared and not drawn. A legend row for it would be a catalogue entry."""
        found = notations_referenced_in(_BODY, _declarations())

        assert set(found) == {"capability", "resource"}

    def test_only_the_sprites_the_body_draws_are_offered(self) -> None:
        referenced = _declarations().referenced_in(_BODY)

        assert referenced.sprites == frozenset({"capability"})

    def test_styling_a_stereotype_is_not_drawing_one(self) -> None:
        """The distinction that cost a wrong legend row on every stored diagram.

        A stored body carries its own `skinparam rectangle<<name>>` blocks inlined, and that glyph
        names a stereotype without drawing anything with it. Read as a reference, a body reported
        every kind it *styles* as a kind it *draws* — so the legend named a fill for a kind no
        element on the picture carried.
        """
        body = "@startuml\n" + _STEREOTYPES + "@enduml\n"

        found = notations_referenced_in(body, _declarations())

        assert found == {}

    def test_an_inlined_block_does_not_keep_a_recoloured_kind_in_the_legend(self) -> None:
        """The case it showed up in. Every `capability` on this body carries its own fill, so the
        kind's declared colour is genuinely off the picture — and the inlined block that styles it is
        not evidence to the contrary."""
        body = (
            "@startuml\n" + _STEREOTYPES
            + 'rectangle "Alpha" <<capability>> as CAP_a #back:ffffff;line:48391c;text:252327\n'
            + "@enduml\n"
        )

        found = notations_referenced_in(body, _declarations())

        assert set(found) == {"capability"}
        assert all(overrides_colour(line) for line in body.splitlines() if " as " in line)

    def test_a_sprite_already_inlined_is_not_injected_twice(self) -> None:
        """The distinction the expansion path depends on, asked through the same reader."""
        body = _BODY + "sprite $archimate_capability <svg/>\n"

        referenced = _declarations().referenced_in(body)

        assert referenced.sprites == frozenset({"capability"})
        assert referenced.sprites_to_inject == frozenset()


class TestHowTheRowsRead:
    def test_two_kinds_sharing_a_colour_are_one_row(self) -> None:
        """Otherwise a reader gets two rows with identical swatches and no way to tell which explains
        the box in front of them. The colour is the mark, and a row is about a mark."""
        rows = colour_rows({"capability": "#EFBD5D", "resource": "#EFBD5D"}, means="element kinds")

        assert len(rows) == 2  # one heading, one colour
        assert rows[1].cells[1].text == "capability, resource"

    def test_the_colour_heading_says_what_the_fills_mean(self) -> None:
        """Under an ad-hoc colouring the fills mean something else entirely, and a heading still
        saying "element kinds" would describe the wrong question."""
        rows = colour_rows({"lower": "#fbbf24"}, means="investment_level")

        assert rows[0].heading is True
        assert rows[0].cells[1].text == "investment_level"

    def test_a_shape_groups_every_kind_drawn_with_it(self) -> None:
        """A corner shape says what *kind* of thing an element is, so twelve motivation types drawn
        with cut corners are one fact, not twelve rows."""
        rows = shape_rows(notations_referenced_in(_BODY, _declarations()))

        by_shape = {row.cells[0].text: row.cells[1].text for row in rows[1:]}
        assert by_shape == {"rounded corners": "Capability", "square corners": "Resource"}

    def test_a_glyph_row_references_the_sprite_the_body_defines(self) -> None:
        rows = glyph_rows(["capability"])

        assert rows[1].cells[0].sprite == "archimate_capability"

    def test_an_arrow_is_drawn_with_both_its_ends(self) -> None:
        """The mark itself, not a sentence about it. A reader matches a legend row to an edge by
        looking, and "ball at the source, filled arrowhead at the target" makes them translate first.

        The glyphs are what the pinned jar renders in a table cell, which is the constraint the first
        version of this row read as "a table cell cannot draw a line" — it can, given characters the
        font has.
        """
        rows = arrow_rows({
            "archimate-assignment": RelationNotation(line="solid", source="ball", target="filled-arrow"),
        })

        assert rows[1].cells[0].text == "\u25cf\u2500\u2500\u2500\u25b6"
        assert rows[1].cells[1].text == "Assignment"

    def test_an_end_with_no_marker_draws_the_line_alone(self) -> None:
        rows = arrow_rows({"archimate-association": RelationNotation(line="solid", target="none")})

        assert rows[1].cells[0].text == "\u2500\u2500\u2500"

    def test_a_dashed_line_is_drawn_dashed(self) -> None:
        """The three line styles have to be distinguishable at a glance, or the column says nothing
        beyond "there is an edge"."""
        drawn = {
            name: arrow_rows({"archimate-x": RelationNotation(line=name, target="hollow-triangle")})[1].cells[0].text
            for name in ("solid", "dashed", "dotted")
        }

        assert len(set(drawn.values())) == 3
        assert drawn["dashed"] == "\u254c\u254c\u254c\u25b7"

    def test_nothing_to_explain_produces_no_heading_either(self) -> None:
        assert shape_rows({}) == ()
        assert glyph_rows([]) == ()
        assert arrow_rows({}) == ()
        assert colour_rows({}, means="element kinds") == ()


class TestHowALabelReads:
    def test_the_ontology_prefix_is_dropped(self) -> None:
        """It says which modelling language this is, which a reader of the diagram already knows —
        the same thing the search result labels do with it."""
        assert readable_label("archimate-assignment") == "Assignment"

    def test_a_sprite_key_reads_as_words(self) -> None:
        assert readable_label("application_component") == "Application Component"

    def test_a_generated_container_stereotype_reads_as_words(self) -> None:
        assert readable_label("StrategyGrouping") == "Strategy Grouping"
