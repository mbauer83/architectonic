"""The reader of PlantUML's SVG answers with the whole picture, or names what stopped it.

PlantUML's SVG structure is another project's output. A layout is harvested from this reading and
written back to the diagram, so a reading that skipped what it did not recognise would write a
diagram with shapes or relations silently gone. Every fixture here is a small picture with exactly
one thing about it that the reader does not know, and each must come back `NotReadable` — never a
picture with that one thing left out.

The fixtures are hand-written and committed: what they hold is deliberately *not* what PlantUML
emits today. The reading of what it does emit is held against real renders in
`test_a_rendered_picture_gives_up_its_geometry.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import MarkShape, NotReadable, RenderedPicture
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from src.infrastructure.rendering.layout.svg_path_data import UnreadablePath, read_path

_FIXTURES = Path(__file__).parent / "fixtures" / "rendered_pictures"


def _read(name: str) -> RenderedPicture | NotReadable:
    return read_rendered_picture((_FIXTURES / name).read_text(encoding="utf-8"))


def _fixtures(prefix: str) -> list[str]:
    return sorted(path.name for path in _FIXTURES.glob(f"{prefix}-*.svg"))


def test_there_are_fixtures_of_each_kind() -> None:
    """A glob that matched nothing would pass every parametrised test below by running none."""
    assert len(_fixtures("unreadable")) >= 12  # noqa: PLR2004 — the cases written when the reader was
    assert len(_fixtures("unread")) >= 3  # noqa: PLR2004


class TestTheSmallPictureItCanRead:
    """The control: the same picture the unreadable fixtures are each one change away from."""

    @pytest.fixture
    def picture(self) -> RenderedPicture:
        read = _read("readable.svg")
        assert isinstance(read, RenderedPicture), read
        return read

    def test_every_shape_is_there_by_its_alias_with_its_box(self, picture: RenderedPicture) -> None:
        assert set(picture.elements) == {"ACT_a", "ACT_b", "JNA_c"}
        assert set(picture.boxes) == {"DOM_business"}
        assert picture.elements["ACT_a"].extent == Extent(40, 80, 140, 120)
        assert picture.elements["JNA_c"].extent == Extent(182, 222, 198, 238)
        assert picture.canvas == Extent(0, 0, 400, 300)

    def test_nesting_is_read_from_the_name_and_borne_out_by_the_drawing(self, picture: RenderedPicture) -> None:
        assert picture.elements["ACT_a"].inside == "DOM_business"
        assert picture.elements["JNA_c"].inside is None
        assert picture.boxes["DOM_business"].inside is None

    def test_words_keep_their_measured_widths_and_the_spaces_are_dropped(self, picture: RenderedPicture) -> None:
        words = picture.elements["ACT_a"].words

        assert [(word.text, word.start, word.width) for word in words] == [
            ("Alpha", Point(50, 104), 30.5), ("One", Point(84.5, 104), 24.25),
        ]
        assert picture.elements["ACT_a"].label == "Alpha One"
        assert picture.boxes["DOM_business"].label == "Business"
        assert picture.elements["JNA_c"].label == ""

    def test_a_relation_has_its_ends_its_line_its_mark_and_its_label(self, picture: RenderedPicture) -> None:
        serves = picture.relations[0]

        assert serves.ends == ("ACT_a", "ACT_b")
        assert serves.line_type == "dependency"
        assert serves.path == (Point(140, 100), Point(234, 100)), "a curve's control points are not on the path"
        assert len(serves.course) > len(serves.path), "the course follows the curve"
        assert serves.first_marks == ()
        assert [mark.shape for mark in serves.second_marks] == [MarkShape.POLYGON]
        assert serves.second_marks[0].filled
        assert (serves.label, serves.words[0].width) == ("serves", 33)

    def test_a_line_drawn_from_its_second_end_is_turned_to_run_from_its_first(self, picture: RenderedPicture) -> None:
        """The layout engine may draw a link backwards; the ends stay as the renderer names them and
        the line is turned, so "the first point" always means "at the first end"."""
        joined = picture.relations[1]

        assert joined.ends == ("JNA_c", "ACT_b")
        assert joined.path == (Point(198, 230), Point(290, 230), Point(290, 120))


@pytest.mark.parametrize("name", _fixtures("unreadable"))
def test_a_picture_with_one_thing_it_does_not_know_is_not_read_at_all(name: str) -> None:
    read = _read(name)

    assert isinstance(read, NotReadable), f"{name} was read, with the unknown part left out: {read}"
    assert read.met, "what was met is the whole of what a caller can report"
    assert read.stated_the_kind_read, f"{name} claims to be the kind that is read; the contract moved"


@pytest.mark.parametrize("name", _fixtures("unread"))
def test_another_kind_of_picture_is_unread_without_being_a_broken_one(name: str) -> None:
    """A sequence chart, a native drawing, a document that is not safe XML: nothing was expected of
    them, so a caller is told they are not read and is not told the contract moved."""
    read = _read(name)

    assert isinstance(read, NotReadable)
    assert not read.stated_the_kind_read


@pytest.mark.parametrize("document", ["", "not svg at all", "<svg", "<html/>", '<svg xmlns="http://www.w3.org/2000/svg"/>'])
def test_anything_that_is_not_a_picture_is_an_answer_and_never_an_exception(document: str) -> None:
    assert isinstance(read_rendered_picture(document), NotReadable)


def test_an_entity_is_refused_rather_than_expanded() -> None:
    """Untrusted input: a body's author controls what PlantUML is asked to draw."""
    read = _read("unread-declares-an-entity.svg")

    assert isinstance(read, NotReadable)
    assert "safe XML" in read.met


class TestPathData:
    def test_lines_and_curves_give_their_ends_and_a_curve_is_walked(self) -> None:
        reading = read_path("M0,0 L10,0 C10,10 20,10 20,0")

        assert reading.through == (Point(0, 0), Point(10, 0), Point(20, 0))
        assert reading.course[0] == Point(0, 0)
        assert reading.course[-1] == Point(20, 0)
        assert max(point.y for point in reading.course) == pytest.approx(7.5), "the curve's apex, not its chord"

    def test_a_command_repeats_over_its_numbers(self) -> None:
        assert read_path("M0,0 L10,0 20,5").through == (Point(0, 0), Point(10, 0), Point(20, 5))

    def test_a_closed_path_returns_to_its_start(self) -> None:
        assert read_path("M0,0 L10,0 L10,10 Z").course[-1] == Point(0, 0)

    @pytest.mark.parametrize("d", ["", "M0,0 l5,5", "M0,0 S1,1 2,2", "M0,0 L1", "C1,1 2,2 3,3", "M0,0 L1,x", "M0,0 H5"])
    def test_what_plantuml_does_not_write_is_refused_not_approximated(self, d: str) -> None:
        with pytest.raises(UnreadablePath):
            read_path(d)
