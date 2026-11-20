"""What the verifier says about a rendered picture: W371–W374, warnings, one per kind per diagram.

The geometry is tested where it is decided (`tests/domain/test_what_a_pictures_geometry_decides.py`).
Here it is what becomes of a decision: which code, which severity, what the message names, what
rides in the details — and what is deliberately *not* said, because an advisory count that reported
on every dense view would be a warning nobody reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_rendered_picture import (
    PICTURE_BESIDE_ITS_SOURCE,
    UNREAD_PICTURE_CODE,
    RenderedPictureRule,
    add_picture_issues,
    issues_for_picture_in,
    picture_issues,
    require_a_directory_each,
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

    def test_the_codes_are_five_of_their_own(self) -> None:
        """W370–W374; the rest of W37x and all of E37x are left for a stated layout's rules."""
        from src.application.verification._verifier_rules_rendered_picture import _CODE_OF

        assert sorted([UNREAD_PICTURE_CODE, *_CODE_OF.values()]) == ["W370", "W371", "W372", "W373", "W374"]


class _Recording:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def check(self, svg: str, loc: str) -> list[Issue]:
        self.seen.append((svg, loc))
        return [Issue(Severity.WARNING, "W371", "found", loc)]


class TestWhichPictureIsRead:
    def test_the_one_picture_in_a_directory_is_handed_over(self, tmp_path: Path) -> None:
        (tmp_path / "whatever-plantuml-called-it.svg").write_text("<svg>one</svg>", encoding="utf-8")
        checks = _Recording()

        assert [issue.code for issue in issues_for_picture_in(tmp_path, checks, _LOC)] == ["W371"]
        assert checks.seen == [("<svg>one</svg>", _LOC)]

    @pytest.mark.parametrize("pictures", [0, 2])
    def test_no_picture_or_several_is_nothing_to_speak_of(self, tmp_path: Path, pictures: int) -> None:
        for number in range(pictures):
            (tmp_path / f"{number}.svg").write_text("<svg/>", encoding="utf-8")
        checks = _Recording()

        assert issues_for_picture_in(tmp_path, checks, _LOC) == []
        assert checks.seen == []

    def test_a_batch_reads_each_picture_beside_its_own_source(self, tmp_path: Path) -> None:
        sources = []
        for name in ("first", "second"):
            source = tmp_path / name / "same-name.puml"
            (source.parent / PICTURE_BESIDE_ITS_SOURCE).mkdir(parents=True)
            (source.parent / PICTURE_BESIDE_ITS_SOURCE / "same.svg").write_text(f"<svg>{name}</svg>", encoding="utf-8")
            sources.append(source)
        checks = _Recording()
        issues_by_path: dict[Path, list[Issue]] = {source: [] for source in sources}

        add_picture_issues(issues_by_path, checks)

        assert checks.seen == [("<svg>first</svg>", str(sources[0])), ("<svg>second</svg>", str(sources[1]))]
        assert all(len(issues) == 1 for issues in issues_by_path.values())

    def test_a_source_plantuml_refused_has_its_error_picture_left_unread(self, tmp_path: Path) -> None:
        """PlantUML draws a refused body too, as a picture of its error message."""
        source = tmp_path / "broken" / "x.puml"
        (source.parent / PICTURE_BESIDE_ITS_SOURCE).mkdir(parents=True)
        (source.parent / PICTURE_BESIDE_ITS_SOURCE / "x.svg").write_text("<svg/>", encoding="utf-8")
        refused = Issue(Severity.ERROR, "E350", "PlantUML: Syntax Error?", str(source))
        checks = _Recording()
        issues_by_path = {source: [refused]}

        add_picture_issues(issues_by_path, checks)

        assert issues_by_path == {source: [refused]}
        assert checks.seen == []

    def test_two_sources_in_one_directory_are_refused_before_anything_is_rendered(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="directory of its own"):
            require_a_directory_each([tmp_path / "a.puml", tmp_path / "b.puml"])
        require_a_directory_each([tmp_path / "1" / "a.puml", tmp_path / "2" / "a.puml"])
