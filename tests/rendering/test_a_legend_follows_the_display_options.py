"""The legend a reader gets for the display options they set.

The row builders are tested one by one beside them; this is the composition — which sections appear,
in what order, and what the colour section says once the fills stop meaning element kinds. That is the
requirement in one sentence: a legend must be *sensitive to the display options changing*, and nothing
covered the sentence.

The colour section is where it matters. Under an ad-hoc colouring the fills are the reader's own, and a
legend still listing element kinds beside a heat map describes colours the picture no longer uses —
which is worse than no legend at all, because a reader trusts it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.viewpoints.viewpoint_style_values import AD_HOC_RAMP_TOKENS, token_color
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.diagram_legend_for_reading import (
    body_with_reading_legend,
    can_explain_notation,
)
from src.infrastructure.rendering.diagram_notation_in_use import (
    notation_in_use,
    types_drawn_as_lines,
    types_drawn_as_nesting,
)

_STEREOTYPES = """\
skinparam rectangle<<capability>> {
  BackgroundColor #f7e7c6
  BorderColor #b08d3f
  RoundCorner 12
}
"""

_BODY = """\
@startuml
rectangle "Plan" <<capability>> as plan
@enduml
"""

#: The same, drawing one edge — `notation_in_use` reads the body to decide which types are lines, so a
#: body with no edge legitimately yields no relationship rows.
_BODY_WITH_EDGE = """\
@startuml
rectangle "Plan" <<capability>> as plan
rectangle "Build" <<capability>> as build
plan --> build
@enduml
"""


@pytest.fixture
def declarations() -> ArchimateDeclarations:
    return ArchimateDeclarations.from_includes(stereotypes=_STEREOTYPES, glyphs="", relations="")


def _legend_of(body: str) -> list[str]:
    """The legend's own lines, so a test reads the table and not the diagram."""
    at = body.rfind("legend ")
    return [] if at == -1 else body[at:].splitlines()


def _sections(body: str) -> dict[tuple[str, str], list[str]]:
    """The legend's rows grouped by the `(mark, meaning)` its heading states.

    Keyed on the **pair**, because neither column alone identifies a section: `colour` heads two of
    them under an ad-hoc colouring — the attribute and the element kinds — while `element kinds` is the
    meaning of both the `colour` and the `shape` section. An assertion looking for either alone is
    satisfied by the wrong rows, and one of these tests passed that way before this existed.
    """
    out: dict[tuple[str, str], list[str]] = {}
    current: tuple[str, str] | None = None
    for line in _legend_of(body):
        if line.startswith("|="):
            cells = [c.strip() for c in line.strip().strip("|").lstrip("=").split("|=")]
            current = (cells[0].strip(), cells[1].strip() if len(cells) > 1 else "")
            out[current] = []
        elif line.startswith("|") and current is not None:
            out[current].append(line)
    return out


def _meanings(body: str) -> set[str]:
    """The meaning column of every `colour` section — what a fill stands for on this picture."""
    return {meaning for mark, meaning in _sections(body) if mark == "colour"}


class TestWhetherThereIsOneAtAll:
    def test_a_body_is_untouched_when_no_legend_is_asked_for(self, declarations: ArchimateDeclarations) -> None:
        out = body_with_reading_legend(_BODY, lens=ReadingLens(), declarations=declarations)

        assert out == _BODY

    def test_the_legend_goes_before_the_last_enduml(self, declarations: ArchimateDeclarations) -> None:
        # PlantUML stops reading at `@enduml`, so a legend after it is silently nothing.
        out = body_with_reading_legend(_BODY, lens=ReadingLens(legend=True), declarations=declarations)

        assert out.rindex("endlegend") < out.rindex("@enduml")


class TestWhatTheColourSectionMeansNow:
    def test_the_fills_mean_element_kinds_while_nothing_is_coloured_by(
        self, declarations: ArchimateDeclarations
    ) -> None:
        lines = _legend_of(body_with_reading_legend(
            _BODY, lens=ReadingLens(legend=True), declarations=declarations
        ))

        assert any("element kinds" in line for line in lines)
        assert any("#f7e7c6" in line for line in lines)

    def test_a_bounded_attribute_lists_its_members_with_their_colours(
        self, declarations: ArchimateDeclarations
    ) -> None:
        lines = _legend_of(body_with_reading_legend(
            _BODY,
            lens=ReadingLens(colour_by="Lifecycle State", legend=True),
            declarations=declarations,
            members=("Planned", "Active"),
        ))

        # The *colour* heading is the attribute now. The shape section still says "element kinds",
        # which is why this looks at the first heading rather than at the table as a whole.
        assert lines[1].startswith("|=") and "Lifecycle State" in lines[1]
        assert "element kinds" not in lines[1]
        assert any("Planned" in line for line in lines)
        assert any("Active" in line for line in lines)

    def test_a_member_row_does_not_repeat_the_attribute_the_heading_names(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """The attribute names itself once. Prefixing every row with it too made the value column the
        widest in the table and pushed each swatch away from the value it stands for."""
        lines = _legend_of(body_with_reading_legend(
            _BODY,
            lens=ReadingLens(colour_by="Lifecycle State", legend=True),
            declarations=declarations,
            members=("Planned",),
        ))

        assert sum("Lifecycle State" in line for line in lines) == 1

    def test_the_readers_own_colour_for_a_member_is_the_one_shown(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """The key and the picture come from one lens, so a legend showing the declared colour beside a
        picture drawn in the reader's would be a legend that lies."""
        lines = _legend_of(body_with_reading_legend(
            _BODY,
            lens=ReadingLens(colour_by="Lifecycle State", key={"Planned": "#123456"}, legend=True),
            declarations=declarations,
            members=("Planned", "Active"),
        ))

        assert any("#123456" in line for line in lines)

    def test_an_unbounded_attribute_shows_the_two_ends_of_its_gradient(
        self, declarations: ArchimateDeclarations
    ) -> None:
        lines = _legend_of(body_with_reading_legend(
            _BODY, lens=ReadingLens(colour_by="risk_score", legend=True), declarations=declarations
        ))

        assert any("lower" in line for line in lines)
        assert any("higher" in line for line in lines)
        assert any(token_color(AD_HOC_RAMP_TOKENS[0]) in line for line in lines)

    def test_a_reader_chosen_gradient_is_the_one_shown(self, declarations: ArchimateDeclarations) -> None:
        lines = _legend_of(body_with_reading_legend(
            _BODY,
            lens=ReadingLens(colour_by="risk_score", ramp=("#111111", "#eeeeee"), legend=True),
            declarations=declarations,
        ))

        assert any("#111111" in line for line in lines)
        assert any("#eeeeee" in line for line in lines)


class TestTheOfferAndTheLegendReadOneNotation:
    """The control is offered from the same reading the legend is drawn from.

    Two routes need this pair — the one that answers whether to show the checkbox, and the one that
    draws the picture — and they assembled it separately at first. A control offered from one reading
    beside a legend drawn from another is a checkbox that does nothing, which is the failure
    `can_explain_notation` exists to prevent; assembling the pair twice reintroduced it one level up.
    """

    def test_a_diagram_offered_the_control_gets_a_legend_with_rows(self, tmp_path: Path) -> None:
        notation = notation_in_use(
            _BODY_WITH_EDGE,
            (("archimate-triggering", "plan", "build"),),
            repo_root=tmp_path,
            relation_notations={"archimate-triggering": {"line": "solid", "target": "filled-arrow"}},
        )

        offered = can_explain_notation(
            _BODY_WITH_EDGE,
            declarations=notation.declarations,
            connection_notations=notation.connection_notations,
        )
        lines = _legend_of(body_with_reading_legend(
            _BODY_WITH_EDGE,
            lens=ReadingLens(legend=True),
            declarations=notation.declarations,
            connection_notations=notation.connection_notations,
        ))

        assert offered is True
        assert any("Triggering" in line for line in lines)

    def test_a_diagram_with_no_notation_is_offered_nothing_and_gets_nothing(self, tmp_path: Path) -> None:
        """An empty repository declares no stereotypes, and no connection is placed — which is the
        activity diagram's case, and the one that must withhold the control."""
        bare = "@startuml\n:step;\n@enduml\n"
        notation = notation_in_use(bare, (), repo_root=tmp_path, relation_notations={})

        offered = can_explain_notation(
            bare, declarations=notation.declarations, connection_notations=notation.connection_notations
        )
        out = body_with_reading_legend(
            bare,
            lens=ReadingLens(legend=True),
            declarations=notation.declarations,
            connection_notations=notation.connection_notations,
        )

        assert offered is False
        assert out == bare

    def test_the_relationship_notations_are_the_ones_the_caller_owns(self, tmp_path: Path) -> None:
        """Passed in, not resolved here. A connection type the caller does not describe gets no row,
        rather than this module reaching for a catalog it has no business knowing about."""
        notation = notation_in_use(
            _BODY_WITH_EDGE,
            (("archimate-triggering", "plan", "build"), ("archimate-flow", "plan", "build")),
            repo_root=tmp_path,
            relation_notations={"archimate-triggering": {"line": "solid", "target": "filled-arrow"}},
        )

        assert set(notation.connection_notations) == {"archimate-triggering"}


class TestOnlyTheMarksThePictureUses:
    """A relationship the body draws by *nesting* is not a line, and must not be given a line row.

    PlantUML draws composition and aggregation as containment, and this project's ontology classes
    both as `nesting`, so the renderer puts the child inside the parent and emits no arrow at all. The
    legend read its relationship rows from the **model's** recorded connections, so it drew a filled
    diamond for composition and a hollow one for aggregation beside a picture containing neither —
    which is worse than omitting them, because a reader looks for a mark that is not there.

    Reported on `promote-artifacts`, whose body nests eight functions inside one process and draws
    exactly two arrow shapes: eleven `-->` and one `..|>`.

    **Nesting is a proposal, not an instruction** — `build_visual_nesting` honours a structural edge
    only where it keeps the drawing a forest, and the rest stay arrows. So the answer cannot be "drop
    the nesting-class types": it has to be what this body did, which is why it is read from the body.
    """

    _NESTED = """\
@startuml x
rectangle "Whole" <<capability>> as PRC_a {
rectangle "Part" <<capability>> as FNC_b
}
' Connections
PRC_a --> FNC_c
@enduml
"""

    def test_a_relationship_drawn_only_by_nesting_gets_no_line_row(self) -> None:
        drawn = types_drawn_as_lines(
            self._NESTED,
            connections=(("archimate-composition", "PRC_a", "FNC_b"),),
        )

        assert drawn == frozenset()

    def test_a_relationship_drawn_as_an_arrow_keeps_its_line_row(self) -> None:
        drawn = types_drawn_as_lines(
            self._NESTED,
            connections=(("archimate-triggering", "PRC_a", "FNC_c"),),
        )

        assert drawn == frozenset({"archimate-triggering"})

    def test_a_type_with_one_nested_and_one_drawn_connection_keeps_its_row(self) -> None:
        """Because nesting is a proposal: a second parent cannot be nested and stays an arrow, so the
        type *is* in the picture as a line and a reader needs to know what it looks like."""
        drawn = types_drawn_as_lines(
            self._NESTED,
            connections=(
                ("archimate-composition", "PRC_a", "FNC_b"),
                ("archimate-composition", "PRC_a", "FNC_c"),
            ),
        )

        assert drawn == frozenset({"archimate-composition"})

    def test_a_connection_the_body_draws_nowhere_gets_no_row(self) -> None:
        """Silence is not a line. An undrawn connection is a verification concern, and giving it a
        legend row would explain a mark the reader cannot find."""
        drawn = types_drawn_as_lines(
            self._NESTED,
            connections=(("archimate-serving", "PRC_a", "FNC_zzz"),),
        )

        assert drawn == frozenset()

    def test_a_layout_link_is_not_a_line(self) -> None:
        body = "@startuml x\nrectangle A as A\nrectangle B as B\nA -[hidden]down- B\n@enduml\n"

        drawn = types_drawn_as_lines(body, connections=(("archimate-triggering", "A", "B"),))

        assert drawn == frozenset()


class TestNestingIsExplainedToo:
    """Nesting is a mark the picture uses, so a legend that omits it is incomplete.

    Dropping the false line rows for composition and aggregation left the containment they are actually
    drawn as unexplained — the reader now sees no wrong mark and still has nothing telling them that a
    box inside a box *is* a relationship.

    **One row, not one per type.** The drawing is identical for both: `promote-artifacts` composes
    seven of its functions and aggregates the eighth, and nothing in the picture distinguishes them. A
    row each would imply a reader could tell which is which, so the mark is stated once and names what
    it may be.
    """

    _NESTED = """\
@startuml x
rectangle "Whole" <<capability>> as PRC_a {
rectangle "Part" <<capability>> as FNC_b
rectangle "Other" <<capability>> as FNC_c
}
@enduml
"""

    def test_a_nested_relationship_is_reported_as_nesting(self) -> None:
        assert types_drawn_as_nesting(
            self._NESTED, connections=(("archimate-composition", "PRC_a", "FNC_b"),)
        ) == frozenset({"archimate-composition"})

    def test_a_relationship_drawn_as_a_line_is_not_nesting(self) -> None:
        body = "@startuml x\nrectangle A as A\nrectangle B as B\nA --> B\n@enduml\n"

        assert types_drawn_as_nesting(
            body, connections=(("archimate-triggering", "A", "B"),)
        ) == frozenset()

    def test_a_connection_drawn_nowhere_is_not_nesting(self) -> None:
        assert types_drawn_as_nesting(
            self._NESTED, connections=(("archimate-serving", "PRC_a", "FNC_zzz"),)
        ) == frozenset()

    def test_the_legend_names_both_types_on_one_row_where_both_are_nested(
        self, declarations: ArchimateDeclarations
    ) -> None:
        lines = _legend_of(body_with_reading_legend(
            self._NESTED,
            lens=ReadingLens(legend=True),
            declarations=declarations,
            nested_types=("archimate-composition", "archimate-aggregation"),
        ))

        nesting = [line for line in lines if "\u25a3" in line]
        assert len(nesting) == 1
        assert "Composition" in nesting[0] and "Aggregation" in nesting[0]

    def test_a_diagram_that_nests_nothing_gets_no_nesting_section(
        self, declarations: ArchimateDeclarations
    ) -> None:
        lines = _legend_of(body_with_reading_legend(
            _BODY, lens=ReadingLens(legend=True), declarations=declarations, nested_types=()
        ))

        assert not any("\u25a3" in line for line in lines)


class TestBothColouringsAreExplained:
    """An ad-hoc colouring recolours only the entities that *have* a value, so the picture carries two
    colourings at once and the legend has to explain both.

    Reported on a real diagram: colouring `repository-synchronization-git-integration` by
    `Lifecycle State` recoloured the two elements carrying one and left six-plus showing their
    ArchiMate stereotype fill. The rendered SVG holds both palettes — `#0891b2` from the attribute and
    `#e5dfd3`/`#b0d0d9` from the stereotypes — and the legend named only the attribute.

    The first version of this replaced the element-kind rows on the grounds that "a legend still
    listing element kinds beside a heat map would describe colours the picture no longer uses". That
    is false whenever any drawn entity lacks a value for the attribute, which is the ordinary case.

    Only the *fill* is overridden. A recoloured element keeps its stereotype's corner shape and glyph,
    so the shape and glyph sections are unaffected and are not touched here.
    """

    _MIXED = """\
@startuml x
rectangle "Has one" <<capability>> as CAP_a #back:0891b2;line:252327;text:252327
rectangle "Has none" <<capability>> as CAP_b
@enduml
"""

    _ALL_RECOLOURED = """\
@startuml x
rectangle "Has one" <<capability>> as CAP_a #back:0891b2;line:252327;text:252327
@enduml
"""

    def test_the_attribute_and_the_element_kinds_are_both_named(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = (body_with_reading_legend(
            self._MIXED,
            lens=ReadingLens(colour_by="Lifecycle State", legend=True),
            declarations=declarations,
            members=("Planned", "Active"),
        ))

        assert _meanings(body) == {"Lifecycle State", "element kinds"}

    def test_the_element_kind_row_carries_the_fill_still_on_screen(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """Not just the heading — the swatch, so a reader can match it to the box in front of them."""
        sections = _sections(body_with_reading_legend(
            self._MIXED,
            lens=ReadingLens(colour_by="Lifecycle State", legend=True),
            declarations=declarations,
            members=("Planned", "Active"),
        ))

        assert any("#f7e7c6" in row for row in sections[("colour", "element kinds")])

    def test_an_element_kind_whose_every_element_was_recoloured_is_not_named(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """The original reasoning, applied where it is actually true: no element still shows that
        stereotype's fill, so naming it would send a reader looking for a colour that is gone."""
        body = body_with_reading_legend(
            self._ALL_RECOLOURED,
            lens=ReadingLens(colour_by="Lifecycle State", legend=True),
            declarations=declarations,
            members=("Planned", "Active"),
        )

        assert _meanings(body) == {"Lifecycle State"}
        assert not any("#f7e7c6" in line for line in _legend_of(body))

    def test_with_no_attribute_colouring_the_element_kinds_are_still_the_only_section(
        self, declarations: ArchimateDeclarations
    ) -> None:
        assert _meanings(body_with_reading_legend(
            self._MIXED, lens=ReadingLens(legend=True), declarations=declarations
        )) == {"element kinds"}
