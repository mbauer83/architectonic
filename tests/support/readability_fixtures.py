"""The readability rules of a route as cases, for `tests/fixtures/layout_geometry/readability.json`.

Part of the shared fixtures `layout_geometry_fixtures` writes: the rules' tiers as data, the
constants they are stated in, and cases with the Python domain's answers for text crossed (the text
rule), a bend at an end (A), a jog (B), a run along another line or a border (C), and the square
course read back off a drawn line with rounded bends.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.route_quality import (
    END_RUN,
    LINE_CLEARANCE,
    RULE_TIERS,
    SHORTEST_SEGMENT,
    bends_at_ends,
    kinks,
    runs_along,
    square_course,
)
from src.domain.diagrams.layout.text_clearance import BAND_MARGIN, TEXT_PADDING, texts_crossed


def _points(course: Sequence[Point]) -> list[list[float]]:
    return [[point.x, point.y] for point in course]


def _extent(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _course(*pairs: tuple[float, float]) -> tuple[Point, ...]:
    return tuple(Point(x, y) for x, y in pairs)


_BAND = Extent(100, 100, 400, 130)
_LABEL = Extent(200, 200, 260, 214)
_TEXT_CASES = (
    ("a line through a title band", _course((150, 50), (150, 300))),
    ("a line ending on a band's top edge does not enter it", _course((150, 50), (150, 100))),
    ("a line grazing a band's side is not through it", _course((99.5, 50), (99.5, 300))),
    ("a line through a relation's label", _course((150, 207), (300, 207))),
    ("a line clear of both", _course((50, 50), (50, 300), (450, 300))),
)

_BOTH = (True, True)
_ENDS_CASES = (
    ("straight: no bend to sit anywhere", _course((0, 0), (10, 0)), _BOTH),
    ("both runs long enough", _course((0, 0), (40, 0), (40, 100), (80, 100)), _BOTH),
    ("a bend right behind the source", _course((0, 0), (20, 0), (20, 100), (80, 100)), _BOTH),
    ("a bend right behind the target", _course((0, 0), (40, 0), (40, 100), (60, 100)), _BOTH),
    ("exactly the run, give or take rounding", _course((0, 0), (END_RUN - 0.4, 0), (END_RUN - 0.4, 50)), _BOTH),
    ("a short run at an end with no decoration", _course((0, 0), (20, 0), (20, 100), (25, 100)), (True, False)),
)

_KINK_CASES = (
    ("no jog", _course((0, 0), (40, 0), (40, 100), (80, 100))),
    ("a jog of ten", _course((0, 0), (40, 0), (40, 10), (80, 10), (80, 60))),
    ("a jog exactly a readable segment", _course((0, 0), (40, 0), (40, SHORTEST_SEGMENT), (80, SHORTEST_SEGMENT))),
    ("short first and last runs are not jogs", _course((0, 0), (5, 0), (5, 100), (10, 100))),
    ("going round something turns back once", _course((0, 0), (60, 0), (60, 80), (-20, 80), (-20, 160))),
    ("a weave turns back twice", _course(
        (694, 268), (694, 378), (635, 378), (635, 460), (663, 460), (663, 596), (623, 596), (623, 630), (665, 630),
    )),
)

_BOX = Extent(100, 100, 300, 200)
_ALONG_CASES = (
    ("runs along a border inside it", _course((50, 104), (250, 104), (250, 300)), [], [_BOX]),
    ("crosses a border at a right angle", _course((150, 50), (150, 150)), [], [_BOX]),
    ("runs along another route", _course((0, 50), (200, 50)), [_course((100, 53), (300, 53))], []),
    ("parallel to another route a clearance away", _course((0, 50), (200, 50)), [_course((100, 56), (300, 56))], []),
    ("collinear with another route but not sharing a stretch", _course((0, 50), (100, 50)),
     [_course((101, 50), (300, 50))], []),
    ("crosses another route", _course((0, 50), (200, 50)), [_course((100, 0), (100, 100))], []),
)

_ROUNDED = (
    ("a line with two rounded bends",
     _course((0, 0), (34, 0), (40, 6), (40, 94), (46, 100), (80, 100))),
    ("a line drawn with sharp bends", _course((0, 0), (40, 0), (40, 100))),
)


def build_readability() -> dict[str, object]:
    return {
        "tiers": dict(RULE_TIERS),
        "constants": {
            "END_RUN": END_RUN, "SHORTEST_SEGMENT": SHORTEST_SEGMENT,
            "LINE_CLEARANCE": LINE_CLEARANCE, "TEXT_PADDING": TEXT_PADDING, "BAND_MARGIN": BAND_MARGIN,
        },
        "text": [
            {"name": name, "course": _points(course),
             "regions": {"band": _extent(_BAND), "label": _extent(_LABEL)},
             "crossed": list(texts_crossed(course, {"band": _BAND, "label": _LABEL}))}
            for name, course in _TEXT_CASES
        ],
        "bends_at_ends": [
            {"name": name, "course": _points(course), "decorated": list(decorated),
             "breaches": [breach.value for breach in bends_at_ends(course, decorated)]}
            for name, course, decorated in _ENDS_CASES
        ],
        "kinks": [
            {"name": name, "course": _points(course), "segments": list(kinks(course))}
            for name, course in _KINK_CASES
        ],
        "runs_along": [
            {"name": name, "course": _points(course), "others": [_points(other) for other in others],
             "borders": [_extent(border) for border in borders],
             "segments": list(runs_along(course, others, borders))}
            for name, course, others, borders in _ALONG_CASES
        ],
        "square": [
            {"name": name, "through": _points(through), "course": _points(square_course(through))}
            for name, through in _ROUNDED
        ],
    }
