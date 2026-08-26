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
    notation_in_use,
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


@pytest.fixture
def declarations() -> ArchimateDeclarations:
    return ArchimateDeclarations.from_includes(stereotypes=_STEREOTYPES, glyphs="", relations="")


def _legend_of(body: str) -> list[str]:
    """The legend's own lines, so a test reads the table and not the diagram."""
    at = body.rfind("legend ")
    return [] if at == -1 else body[at:].splitlines()


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
            ["archimate-triggering"],
            repo_root=tmp_path,
            relation_notations={"archimate-triggering": {"line": "solid", "target": "filled-arrow"}},
        )

        offered = can_explain_notation(
            _BODY,
            declarations=notation.declarations,
            connection_notations=notation.connection_notations,
        )
        lines = _legend_of(body_with_reading_legend(
            _BODY,
            lens=ReadingLens(legend=True),
            declarations=notation.declarations,
            connection_notations=notation.connection_notations,
        ))

        assert offered is True
        assert any("triggering" in line for line in lines)

    def test_a_diagram_with_no_notation_is_offered_nothing_and_gets_nothing(self, tmp_path: Path) -> None:
        """An empty repository declares no stereotypes, and no connection is placed — which is the
        activity diagram's case, and the one that must withhold the control."""
        notation = notation_in_use([], repo_root=tmp_path, relation_notations={})
        bare = "@startuml\n:step;\n@enduml\n"

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
            ["archimate-triggering", "archimate-flow"],
            repo_root=tmp_path,
            relation_notations={"archimate-triggering": {"line": "solid", "target": "filled-arrow"}},
        )

        assert set(notation.connection_notations) == {"archimate-triggering"}
