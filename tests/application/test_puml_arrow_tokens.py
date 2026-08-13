"""Where a direction and a line style go inside a PlantUML arrow token.

Three implementations of the direction insert existed and two were live and identical, so nothing
failed and nothing said they were both there. These assertions are stated over the token forms the
ontology actually declares — including the containment arrows, which none of the three could take.
"""

from __future__ import annotations

import pytest

from src.application.puml_arrow_tokens import insert_arrow_direction, insert_arrow_line_style


class TestInsertingADirection:
    @pytest.mark.parametrize(
        ("arrow", "expected"),
        [
            ("-->", "-down->"),
            ("--", "-down-"),
            ("-|>", "-down-|>"),
            ("--|>", "-down-|>"),
            ("..>", ".down.>"),
            ("..|>", ".down.|>"),
            ("-[#red]->", "-[#red]down->"),
        ],
    )
    def test_the_direction_goes_inside_the_line(self, arrow: str, expected: str) -> None:
        assert insert_arrow_direction(arrow, "down") == expected

    @pytest.mark.parametrize(
        ("arrow", "expected"),
        [
            ("o--", "o-down-"),
            ("*--", "*-down-"),
            ("o->", "o-down->"),
            # An arrowhead at the source is a marker too — a line drawn back the way it is read.
            # This sat in the "cannot take one" list below on the assumption that it could not,
            # so every such token silently lost its rank hint. `<-down-` renders; measured.
            ("<--", "<-down-"),
        ],
    )
    def test_a_source_marker_keeps_its_place_ahead_of_the_direction(
        self, arrow: str, expected: str
    ) -> None:
        """PlantUML draws the containment diamond at the source: `o-down-`, never `-downo-`.
        Every earlier implementation returned these unchanged, which silently dropped the rank
        hint from exactly the relations ArchiMate draws as containment."""
        assert insert_arrow_direction(arrow, "down") == expected

    @pytest.mark.parametrize("arrow", ["-[hidden]down-", "-down->", "o-up-", "***>"])
    def test_a_token_that_cannot_take_one_is_returned_unchanged(self, arrow: str) -> None:
        """A hidden link, a token already stating a direction, and anything unrecognised."""
        assert insert_arrow_direction(arrow, "left") == arrow


class TestInsertingALineStyle:
    @pytest.mark.parametrize(
        ("arrow", "expected"),
        [
            ("-->", "-[dashed]->"),
            ("..>", ".[dotted].>"),
            # The marker is not part of the line, so the bracket goes after it, inside the line.
            ("o--", "o-[dashed]-"),
        ],
    )
    def test_the_style_goes_where_the_line_begins(self, arrow: str, expected: str) -> None:
        style = "dotted" if arrow.startswith(".") else "dashed"
        assert insert_arrow_line_style(arrow, style) == expected

    @pytest.mark.parametrize("arrow", ["-[dashed]->", "-down->", "-[hidden]-"])
    def test_a_token_already_decorated_is_left_alone(self, arrow: str) -> None:
        assert insert_arrow_line_style(arrow, "dotted") == arrow

    def test_no_style_is_no_change(self) -> None:
        assert insert_arrow_line_style("-->", "") == "-->"
