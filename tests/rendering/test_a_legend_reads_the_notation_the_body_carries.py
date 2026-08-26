"""What a legend says, read out of the body's own preamble rather than from today's ontology.

That distinction is the point of this file. A body may carry the generated declarations *inlined*, and
an inlined copy is what PlantUML is actually handed — so a legend derived from the ontology would
describe a palette the diagram is not using. This repository has had nine such diagrams at once, all
drawing colours their bodies were authored with. Reading the preamble makes a legend describe the
picture that was drawn.

The other half is that only *referenced* declarations count. `ArchimateDeclarations` holds the whole
catalogue; a body uses a handful of it, and the handful is what a reader needs explained.
"""

from __future__ import annotations

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
        assert by_shape == {"rounded corners": "capability", "square corners": "resource"}

    def test_a_glyph_row_references_the_sprite_the_body_defines(self) -> None:
        rows = glyph_rows(["capability"])

        assert rows[1].cells[0].sprite == "archimate_capability"

    def test_an_arrow_is_described_in_words_at_both_ends(self) -> None:
        """A table cell cannot draw a line, and `relation_notation` states the marks structurally —
        which is why it exists: a PlantUML token has no form for a ball at the source."""
        rows = arrow_rows({
            "archimate-assignment": RelationNotation(line="solid", source="ball", target="filled-arrow"),
        })

        assert rows[1].cells[0].text == "assignment"
        assert rows[1].cells[1].text == "solid line, ball at the source, filled arrowhead at the target"

    def test_an_end_with_no_marker_is_not_mentioned(self) -> None:
        rows = arrow_rows({"archimate-association": RelationNotation(line="solid", target="none")})

        assert rows[1].cells[1].text == "solid line"

    def test_nothing_to_explain_produces_no_heading_either(self) -> None:
        assert shape_rows({}) == ()
        assert glyph_rows([]) == ()
        assert arrow_rows({}) == ()
        assert colour_rows({}, means="element kinds") == ()


class TestHowALabelReads:
    def test_the_ontology_prefix_is_dropped(self) -> None:
        """It says which modelling language this is, which a reader of the diagram already knows —
        the same thing the search result labels do with it."""
        assert readable_label("archimate-assignment") == "assignment"

    def test_a_sprite_key_reads_as_words(self) -> None:
        assert readable_label("application_component") == "application component"

    def test_a_generated_container_stereotype_reads_as_words(self) -> None:
        assert readable_label("StrategyGrouping") == "strategy grouping"
