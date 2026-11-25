"""The box rule as cases, for `tests/fixtures/layout_geometry/boxes.json`.

Part of the shared fixtures `layout_geometry_fixtures` writes: a picture's boxes and elements as the
renderer drew them, where the elements are now and what is stated for a box, and the Python
composer's answer (`arrangement.fitted_boxes`) for where every box is drawn. The canvas's
`fittedBoxes` is held to the same answers, so a change to the padding, the title margin or the
widening on one side fails on the other.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import DrawnBox, DrawnElement, MeasuredWord, RenderedPicture
from src.infrastructure.rendering.layout.arrangement import fitted_boxes

_CANVAS = Extent(0, 0, 800, 600)
#: A grouping G holding A and B, drawn with 10 of padding and a title across its middle.
_G = DrawnBox("G", Extent(10, 10, 250, 90), None, (MeasuredWord("Group", Point(110, 25), 30),))
_A = DrawnElement("A", Extent(20, 40, 120, 80), "G")
_B = DrawnElement("B", Extent(140, 40, 240, 80), "G")
_C = DrawnElement("C", Extent(400, 40, 500, 80), None)
#: An outer box O holding a box I that holds D; and an empty box E with a long title.
_O = DrawnBox("O", Extent(300, 200, 600, 400), None, (MeasuredWord("Outer", Point(430, 215), 40),))
_I = DrawnBox("I", Extent(320, 240, 520, 380), "O", (MeasuredWord("Inner", Point(400, 255), 40),))
_D = DrawnElement("D", Extent(340, 280, 440, 340), "I")
_E = DrawnBox(
    "E", Extent(20, 450, 80, 500), None, (MeasuredWord("A rather long title", Point(25, 465), 120),),
)
_PICTURE = RenderedPicture(
    _CANVAS,
    {element.alias: element for element in (_A, _B, _C, _D)},
    {box.alias: box for box in (_G, _O, _I, _E)},
    (),
)

_CASES: tuple[tuple[str, Mapping[str, Extent], Mapping[str, Extent]], ...] = (
    ("nothing moved: every box as drawn, an empty one widened to its title", {}, {}),
    ("a member moved out grows its box by the padding it had", {"B": Extent(300, 60, 400, 100)}, {}),
    ("members moved in shrink the box, never below its title", {"A": Extent(100, 40, 120, 80),
                                                               "B": Extent(122, 40, 142, 80)}, {}),
    ("a member moved deep grows its box and the box that holds it", {"D": Extent(500, 420, 600, 480)}, {}),
    ("a stated box larger than its contents widens it", {}, {"G": Extent(0, 0, 400, 200)}),
    ("a stated box smaller than its contents never narrows it", {}, {"G": Extent(50, 20, 100, 60)}),
    ("a stated corner alone reaches only that point", {}, {"I": Extent(560, 395, 560, 395)}),
)


def _extent(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _word(word: MeasuredWord) -> dict[str, object]:
    return {"text": word.text, "x": word.start.x, "y": word.start.y, "width": word.width}


def build_boxes() -> dict[str, object]:
    elements = {alias: element.extent for alias, element in _PICTURE.elements.items()}
    return {
        "elements": [
            {"alias": one.alias, "extent": _extent(one.extent), "inside": one.inside}
            for one in _PICTURE.elements.values()
        ],
        "boxes": [
            {"alias": one.alias, "extent": _extent(one.extent), "inside": one.inside,
             "words": [_word(word) for word in one.words]}
            for one in _PICTURE.boxes.values()
        ],
        "cases": [
            {
                "name": name,
                "moved": {alias: _extent(extent) for alias, extent in moved.items()},
                "stated": {alias: _extent(extent) for alias, extent in stated.items()},
                "fitted": {
                    alias: _extent(extent)
                    for alias, extent in fitted_boxes(_PICTURE, {**elements, **moved}, stated.get).items()
                },
            }
            for name, moved, stated in _CASES
        ],
    }
