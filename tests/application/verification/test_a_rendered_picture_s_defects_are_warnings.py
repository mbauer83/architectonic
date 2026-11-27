"""What the verifier says about a rendered picture: W371–W374, warnings, one per kind per diagram.

The geometry is tested where it is decided (`tests/domain/test_what_a_pictures_geometry_decides.py`).
Here it is what becomes of a decision: which code, which severity, what the message names, what
rides in the details — and what is deliberately *not* said, because an advisory count that reported
on every dense view would be a warning nobody reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.plantuml_drawing import Drawn
from src.application.verification._verifier_rules_rendered_picture import (
    UNREAD_PICTURE_CODE,
    DrawnForSource,
    RenderedPictureRule,
    picture_issues,
)
from src.application.verification.artifact_verifier_types import Issue, Severity
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    DrawnRelation,
    MeasuredWord,
    NotReadable,
    RenderedPicture,
)

_LOC = "diagram-catalog/diagrams/ARC@1.x.a-view.puml"


def _named(alias: str, name: str, left: float, top: float, *, inside: str | None = None) -> DrawnElement:
    return DrawnElement(
        alias=alias, extent=Extent(left, top, left + 100, top + 40), inside=inside,
        words=(MeasuredWord(name, Point(left + 10, top + 24), 60),),
    )


def _line(first: str, second: str, *points: tuple[float, float]) -> DrawnRelation:
    course = tuple(Point(x, y) for x, y in points)
    return DrawnRelation(ends=(first, second), line_type="dependency", path=course, course=course)


def _picture(*shapes: DrawnElement | DrawnBox, relations: tuple[DrawnRelation, ...] = ()) -> RenderedPicture:
    return RenderedPicture(
        canvas=Extent(0, 0, 1000, 1000),
        elements={shape.alias: shape for shape in shapes if isinstance(shape, DrawnElement)},
        boxes={shape.alias: shape for shape in shapes if isinstance(shape, DrawnBox)},
        relations=relations,
    )


_THROUGH = _picture(
    _named("A", "Orders", 0, 0), _named("B", "Billing", 400, 0), _named("C", "Shipping", 200, 0),
    relations=(_line("A", "B", (100, 20), (400, 20)),),
)


def _only(issues: list[Issue]) -> Issue:
    assert len(issues) == 1, issues
    return issues[0]


@pytest.mark.verifies("REQ@1795196233.GIvmUuQ")
class TestEachDefectHasItsCode:
    def test_a_relation_through_an_element_is_w371_and_names_all_three(self) -> None:
        issue = _only(picture_issues(_THROUGH, _LOC))

        assert (issue.code, issue.severity, issue.location) == ("W371", Severity.WARNING, _LOC)
        assert "between «Orders» and «Billing» through «Shipping»" in issue.message

    def test_overlapping_shapes_are_w372(self) -> None:
        issue = _only(picture_issues(_picture(_named("A", "Orders", 0, 0), _named("B", "Billing", 50, 10)), _LOC))

        assert issue.code == "W372"
        assert "«Orders» and «Billing»" in issue.message

    def test_a_label_wider_than_its_shape_is_w373(self) -> None:
        words = (MeasuredWord("Far too long a name", Point(10, 24), 160),)
        wide = DrawnElement("A", Extent(0, 0, 100, 40), None, words)

        issue = _only(picture_issues(_picture(wide), _LOC))

        assert issue.code == "W373"
        assert "«Far too long a name»" in issue.message

    def test_a_box_over_a_shape_not_inside_it_is_w374(self) -> None:
        box = DrawnBox("G", Extent(0, 0, 300, 300), None, (MeasuredWord("Front Office", Point(100, 14), 80),))

        issue = _only(picture_issues(_picture(box, _named("S", "Stray", 250, 250)), _LOC))

        assert issue.code == "W374"
        assert "the box «Front Office» over «Stray»" in issue.message

    def test_a_shape_with_no_label_is_named_by_its_alias(self) -> None:
        junction = DrawnElement("JNA_x", Extent(240, 10, 256, 26), None)
        picture = _picture(_named("A", "Orders", 0, 0), _named("B", "Billing", 400, 0), junction,
                           relations=(_line("A", "B", (100, 18), (400, 18)),))

        assert "through the unlabelled shape JNA_x" in _only(picture_issues(picture, _LOC)).message

    def test_no_picture_finding_is_an_error(self) -> None:
        """A layout engine placed these shapes; a write refused over where it put a line is a write
        its author cannot always repair."""
        everything = _picture(
            _named("A", "Orders", 0, 0), _named("B", "Billing", 400, 0), _named("C", "Shipping", 200, 0),
            _named("D", "Dup", 420, 10), DrawnBox("G", Extent(600, 0, 800, 200), None), _named("S", "Stray", 750, 150),
            DrawnElement("W", Extent(0, 500, 50, 540), None, (MeasuredWord("Too wide", Point(0, 524), 90),)),
            relations=(_line("A", "B", (100, 20), (400, 20)),),
        )

        issues = picture_issues(everything, _LOC)

        assert sorted(issue.code for issue in issues) == ["W371", "W372", "W373", "W374"]
        assert {issue.severity for issue in issues} == {Severity.WARNING}


class TestOneFindingPerKind:
    _CROWDED = _picture(*(_named(f"E{n}", f"Element {n}", n * 20, n * 5) for n in range(5)))

    def test_many_places_are_one_warning_that_counts_them(self) -> None:
        issue = _only(picture_issues(self._CROWDED, _LOC))

        assert "10 time(s)" in issue.message
        assert issue.message.count(";") == 3, "three places named, then the rest counted"
        assert issue.message.endswith("and 7 more.")

    def test_every_place_is_in_the_details_by_alias(self) -> None:
        details = _only(picture_issues(self._CROWDED, _LOC)).details

        assert details is not None
        assert len(details["places"]) == 10  # noqa: PLR2004
        assert details["places"][0] == {"shapes": ["E0", "E1"], "described": "«Element 0» and «Element 1»"}


class TestWhatIsOnlyAdvisory:
    _CROSSING = (_line("A", "B", (100, 40), (400, 400)), _line("C", "D", (400, 40), (100, 400)))
    _CORNERS = (_named("A", "A", 0, 0), _named("B", "B", 400, 400), _named("C", "C", 400, 0), _named("D", "D", 0, 400))

    def test_a_picture_that_only_crosses_lines_reports_nothing(self) -> None:
        assert picture_issues(_picture(*self._CORNERS, relations=self._CROSSING), _LOC) == []

    def test_the_counts_ride_in_the_details_of_what_is_reported(self) -> None:
        overlapping = _picture(*self._CORNERS, _named("E", "E", -50, -10), relations=self._CROSSING)

        details = _only(picture_issues(overlapping, _LOC)).details

        assert details is not None
        assert details["advisory"]["crossings"] == 1
        assert details["advisory"]["worst_detour"]["times_the_direct_line"] == pytest.approx(1.0)


class TestAPictureThatCannotBeRead:
    def test_a_picture_of_the_kind_read_that_is_not_readable_is_reported(self) -> None:
        """Silence here would look exactly like a clean picture."""
        unreadable = NotReadable("a group of class 'swimlane'", stated_the_kind_read=True)
        rule = RenderedPictureRule(read=lambda _svg: unreadable)

        issue = _only(rule.check("<svg/>", _LOC))

        assert (issue.code, issue.severity) == (UNREAD_PICTURE_CODE, Severity.WARNING)
        assert "a group of class 'swimlane'" in issue.message and "not checked" in issue.message

    def test_another_kind_of_picture_is_passed_over_in_silence(self) -> None:
        rule = RenderedPictureRule(read=lambda _svg: NotReadable("a picture of PlantUML's SEQUENCE kind"))

        assert rule.check("<svg/>", _LOC) == []

    def test_a_readable_picture_is_checked(self) -> None:
        assert _only(RenderedPictureRule(read=lambda _svg: _THROUGH).check("<svg/>", _LOC)).code == "W371"

    def test_the_codes_are_their_own(self) -> None:
        """W370–W374, and W380–W382 and W384–W386 for what a router answers for; W375–W379 and E37x are a
        stated layout's, and W383 says no route was found."""
        from src.application.verification._verifier_rules_rendered_picture import _CODE_OF

        assert sorted([UNREAD_PICTURE_CODE, *_CODE_OF.values()]) == [
            "W370", "W371", "W372", "W373", "W374", "W380", "W381", "W382", "W384", "W385", "W386",
        ]


class _Recording:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def check(self, svg: str, loc: str) -> list[Issue]:
        self.seen.append((svg, loc))
        return [Issue(Severity.WARNING, "W371", "found", loc)]


class _Drawing:
    """A PlantUML that answers every check with *answer*."""

    def __init__(self, answer: Drawn) -> None:
        self._answer = answer

    def draw_for_check(self, source: str, *, timeout: float) -> Drawn:
        del source, timeout
        return self._answer


@pytest.fixture
def _syntax_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.application.verification import artifact_verifier_syntax

    monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
    monkeypatch.setattr(artifact_verifier_syntax, "find_plantuml_jar", lambda: Path("plantuml.jar"))


@pytest.mark.usefixtures("_syntax_checked")
class TestWhichPictureIsRead:
    @staticmethod
    def _checked(tmp_path: Path, answer: Drawn) -> tuple[list[Issue], _Recording]:
        from src.application.verification.artifact_verifier_syntax import check_puml_syntax

        source = tmp_path / "x.puml"
        source.write_text("@startuml\nA -> B\n@enduml\n", encoding="utf-8")
        checks = _Recording()
        return check_puml_syntax(source, _LOC, drawing=_Drawing(answer), picture_checks=checks), checks

    def test_the_one_picture_drawn_is_handed_over(self, tmp_path: Path) -> None:
        issues, checks = self._checked(tmp_path, Drawn((b"<svg>one</svg>",)))

        assert [issue.code for issue in issues] == ["W371"]
        assert checks.seen == [("<svg>one</svg>", _LOC)]

    @pytest.mark.parametrize("pictures", [0, 2])
    def test_no_picture_or_several_is_nothing_to_speak_of(self, tmp_path: Path, pictures: int) -> None:
        issues, checks = self._checked(tmp_path, Drawn(tuple(b"<svg/>" for _ in range(pictures))))

        assert issues == []
        assert checks.seen == []

    def test_a_source_plantuml_refused_has_its_error_picture_left_unread(self, tmp_path: Path) -> None:
        """PlantUML draws a refused body too, as a picture of its error message."""
        issues, checks = self._checked(tmp_path, Drawn((b"<svg/>",), "ERROR\n1\nSyntax Error?\n"))

        assert [issue.code for issue in issues] == ["E350"]
        assert checks.seen == []


class TestWhatARouterAnswersFor:
    """W380–W382 are decided of every picture and reported only of one a router drew from a layout."""

    _BAND = DrawnBox(
        alias="G", extent=Extent(150, -60, 350, 200), inside=None,
        words=(MeasuredWord("Team", Point(230, -40), 40),),
    )
    _THROUGH_THE_TITLE = _picture(
        _named("A", "Orders", 0, 100), _named("B", "Billing", 400, 100), _BAND,
        relations=(_line("A", "B", (100, 120), (120, 120), (120, -45), (380, -45), (380, 120), (400, 120)),),
    )
    _ALONG_A_BORDER = _picture(
        _named("A", "Orders", 0, 100), _named("B", "Billing", 400, 100), _BAND,
        relations=(_line("A", "B", (50, 140), (50, 197), (450, 197), (450, 140)),),
    )

    def test_a_relation_through_a_box_title_is_w380_on_a_laid_out_picture(self) -> None:
        codes = {issue.code for issue in picture_issues(self._THROUGH_THE_TITLE, _LOC, laid_out=True)}

        assert "W380" in codes

    def test_and_none_of_them_on_a_picture_graphviz_laid_out(self) -> None:
        codes = {issue.code for issue in picture_issues(self._THROUGH_THE_TITLE, _LOC)}

        assert not codes & {"W380", "W381", "W382"}

    def test_a_short_run_at_an_end_with_no_decoration_is_no_w381(self) -> None:
        codes = {issue.code for issue in picture_issues(self._THROUGH_THE_TITLE, _LOC, laid_out=True)}

        assert "W381" not in codes

    def test_a_relation_running_along_a_box_border_is_w382(self) -> None:
        codes = {issue.code for issue in picture_issues(self._ALONG_A_BORDER, _LOC, laid_out=True)}

        assert "W382" in codes

    def test_a_rule_reads_the_picture_drawn_for_the_source_and_asks_the_router_s_rules_of_it(self) -> None:
        read: list[str] = []

        def reader(svg: str) -> RenderedPicture:
            read.append(svg)
            return self._ALONG_A_BORDER

        rule = RenderedPictureRule(read=reader, drawn=lambda svg, loc: DrawnForSource(f"composed {svg}", laid_out=True))
        codes = {issue.code for issue in rule.check("plantuml", _LOC)}

        assert read == ["composed plantuml"]
        assert "W382" in codes


class TestANarrowGap:
    """W384: a gap between two boxes too narrow for the lines laid along it, by its boxes and its shortfall."""

    @staticmethod
    def _box(alias: str, name: str, left: float) -> DrawnBox:
        return DrawnBox(
            alias=alias, extent=Extent(left, 0, left + 200, 300), inside=None,
            words=(MeasuredWord(name, Point(left + 80, 16), 40),),
        )

    # Three lines run upright along the 20 px between two boxes: they need (3 + 1) × 12 = 48.
    _GAP = _picture(
        _box("L", "Resources", 0), _box("R", "Value Streams", 220),
        _named("A", "Orders", 40, 400), _named("B", "Billing", 260, 400),
        relations=tuple(
            _line("A", "B", (90, 400), (90, 380), (x, 380), (x, -20), (310, -20), (310, 0))
            for x in (205, 210, 215)
        ),
    )

    def test_it_names_both_boxes_the_lines_and_how_much_wider_the_gap_must_be(self) -> None:
        issue = next(issue for issue in picture_issues(self._GAP, _LOC, laid_out=True) if issue.code == "W384")

        assert "«Resources» and «Value Streams»" in issue.message
        assert "3 line(s)" in issue.message
        assert "27 px wider" in issue.message  # 48 needed, 20 there, a pixel's rounding allowed
        assert issue.details["places"][0]["wider_by"] == 27  # type: ignore[index]

    def test_lines_crossing_a_gap_do_not_need_its_room(self) -> None:
        crossing = _picture(
            self._box("L", "Resources", 0), self._box("R", "Value Streams", 220),
            _named("A", "Orders", 40, 400), _named("B", "Billing", 260, 400),
            relations=(_line("A", "B", (90, 400), (90, 350), (310, 350), (310, 400)),),
        )

        assert "W384" not in {issue.code for issue in picture_issues(crossing, _LOC, laid_out=True)}

    def test_it_is_asked_only_of_a_picture_a_router_drew(self) -> None:
        assert "W384" not in {issue.code for issue in picture_issues(self._GAP, _LOC)}


class TestARelationLeavingItsBox:
    """W385: two members of a box are joined inside it."""

    _BOX = DrawnBox(
        alias="G", extent=Extent(0, 0, 600, 200), inside=None, words=(MeasuredWord("Team", Point(280, 16), 40),),
    )

    def _with(self, *points: tuple[float, float]) -> RenderedPicture:
        return _picture(
            self._BOX, _named("A", "Orders", 40, 80, inside="G"), _named("B", "Billing", 440, 80, inside="G"),
            relations=(_line("A", "B", *points),),
        )

    def test_a_line_between_two_members_drawn_outside_their_box_is_w385(self) -> None:
        outside = self._with((90, 120), (90, 240), (490, 240), (490, 120))
        issue = next(issue for issue in picture_issues(outside, _LOC, laid_out=True) if issue.code == "W385")

        assert "«Orders» and «Billing», drawn outside «Team»" in issue.message

    def test_one_drawn_inside_it_is_not(self) -> None:
        inside = self._with((140, 100), (440, 100))

        assert "W385" not in {issue.code for issue in picture_issues(inside, _LOC, laid_out=True)}


def test_a_relation_drawn_with_a_slanted_run_is_w386_on_a_laid_out_picture() -> None:
    slanted = _picture(
        _named("A", "Orders", 0, 0), _named("B", "Billing", 400, 40),
        relations=(_line("A", "B", (100, 20), (250, 20), (260, 60), (400, 60)),),
    )

    assert "W386" in {issue.code for issue in picture_issues(slanted, _LOC, laid_out=True)}
    assert "W386" not in {issue.code for issue in picture_issues(_THROUGH, _LOC, laid_out=True)}


def test_a_layout_that_leaves_a_relation_no_route_is_w383() -> None:
    rule = RenderedPictureRule(
        read=lambda svg: _THROUGH, drawn=lambda svg, loc: DrawnForSource(svg, unroutable=("«Orders» and «Billing»",)),
    )
    issues = rule.check("plantuml", _LOC)

    assert issues[0].code == "W383"
    assert "«Orders» and «Billing»" in issues[0].message
