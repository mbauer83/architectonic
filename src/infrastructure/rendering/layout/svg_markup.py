"""Drawing markup, placed again: a copy of what the renderer drew, with every coordinate somewhere else.

The composer re-places PlantUML's own drawing of an element instead of drawing its notation a second
time. It does so by rewriting coordinates, not by wrapping the drawing in a transform: a picture's
shapes are read in absolute coordinates (`plantuml_svg_reader`), and a composed picture has to read
back as what it shows, or every check on a rendered picture would misjudge a laid-out one.

Two ways of placing are enough. A `Motion` turns a drawing about a point and shifts it — a shift
alone for an element, a turn for a decoration that must face along a new final segment. `fitted`
stretches an outline to a new rectangle while every point keeps its distance from the nearest side,
so a cut or rounded corner stays the size it was drawn.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent, Point
from src.infrastructure.rendering.layout._svg_drawing import (
    Unreadable,
    numbers_of,
    outline_extent,
    polygon_corners,
    tag_of,
)
from src.infrastructure.rendering.layout.svg_path_data import UnreadablePath, moved_path, written_number

Mapped = Callable[[float, float], tuple[float, float]]

#: How far above its baseline a line of text reaches, and how far below, as a share of its font size.
_ASCENT, _DESCENT = 0.93, 0.24

_DEFAULT_FONT_SIZE = 12.0


@dataclass(frozen=True)
class Motion:
    """A turn about *pivot* that carries the pivot to *to*. No turn is a plain shift."""

    pivot: Point
    to: Point
    cos: float = 1.0
    sin: float = 0.0

    @classmethod
    def shift(cls, dx: float, dy: float) -> Motion:
        return cls(Point(0.0, 0.0), Point(dx, dy))

    @classmethod
    def facing(cls, pivot: Point, heading: tuple[float, float], to: Point, new_heading: tuple[float, float]) -> Motion:
        """The motion carrying a drawing at *pivot* that faces *heading* to *to*, facing *new_heading*."""
        cos = heading[0] * new_heading[0] + heading[1] * new_heading[1]
        sin = heading[0] * new_heading[1] - heading[1] * new_heading[0]
        return cls(pivot, to, cos, sin)

    @property
    def degrees(self) -> float:
        return math.degrees(math.atan2(self.sin, self.cos))

    @property
    def is_a_quarter_turn(self) -> bool:
        return abs(self.sin) > abs(self.cos)

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = x - self.pivot.x, y - self.pivot.y
        return self.to.x + dx * self.cos - dy * self.sin, self.to.y + dx * self.sin + dy * self.cos


def _set(element: Element, **numbers: float) -> None:
    for name, value in numbers.items():
        element.set(name, written_number(value))


def _moved_box(element: Element, motion: Motion, *, corner: tuple[str, str], size: tuple[str, str]) -> None:
    """A shape stated as a corner and a size: its middle is carried, and a quarter turn swaps its sides."""
    x, y, width, height = numbers_of(element, *corner, *size)
    centre_x, centre_y = motion(x + width / 2, y + height / 2)
    if motion.is_a_quarter_turn:
        width, height = height, width
    placed = {corner[0]: centre_x - width / 2, corner[1]: centre_y - height / 2, size[0]: width, size[1]: height}
    _set(element, **placed)


def _moved_ellipse(element: Element, motion: Motion) -> None:
    cx, cy, rx, ry = numbers_of(element, "cx", "cy", "rx", "ry")
    centre_x, centre_y = motion(cx, cy)
    if motion.is_a_quarter_turn:
        rx, ry = ry, rx
    _set(element, cx=centre_x, cy=centre_y, rx=rx, ry=ry)


def _points_written(points: Iterable[tuple[float, float]]) -> str:
    return ",".join(f"{written_number(x)},{written_number(y)}" for x, y in points)


def _path_through(element: Element, mapped: Mapped, turned_by: float = 0.0) -> None:
    try:
        element.set("d", moved_path(element.get("d") or "", mapped, turned_by=turned_by))
    except UnreadablePath as unreadable:
        raise Unreadable(str(unreadable)) from None


def _move_in_place(element: Element, motion: Motion) -> None:
    tag = tag_of(element)
    if tag == "g":
        for child in element:
            _move_in_place(child, motion)
    elif tag in ("rect", "image"):
        _moved_box(element, motion, corner=("x", "y"), size=("width", "height"))
    elif tag == "ellipse":
        _moved_ellipse(element, motion)
    elif tag == "text":
        x, y = motion(*numbers_of(element, "x", "y"))
        _set(element, x=x, y=y)
    elif tag == "line":
        x1, y1, x2, y2 = numbers_of(element, "x1", "y1", "x2", "y2")
        (x1, y1), (x2, y2) = motion(x1, y1), motion(x2, y2)
        _set(element, x1=x1, y1=y1, x2=x2, y2=y2)
    elif tag == "polygon":
        element.set("points", _points_written(motion(corner.x, corner.y) for corner in polygon_corners(element)))
    elif tag == "path":
        _path_through(element, motion, motion.degrees)
    elif tag not in ("title", "desc"):
        raise Unreadable(f"a <{tag}> in a drawing that is to be placed again")


def moved(element: Element, motion: Motion) -> Element:
    """A copy of *element*, and of everything in it, carried by *motion*. Raises `Unreadable`."""
    placed = copy.deepcopy(element)
    _move_in_place(placed, motion)
    return placed


def fitted(outline: Element, drawn: Extent, to: Extent) -> Element:
    """A copy of *outline*, drawn over *drawn*, stretched to *to* with its corners as they were drawn.

    Every point keeps its distance from the side it is nearer, so the half of the outline towards a
    side moves with that side. Raises `Unreadable` for an outline that cannot be stretched this way.
    """
    middle = drawn.centre

    def stretched(x: float, y: float) -> tuple[float, float]:
        return (
            to.left + (x - drawn.left) if x <= middle.x else to.right - (drawn.right - x),
            to.top + (y - drawn.top) if y <= middle.y else to.bottom - (drawn.bottom - y),
        )

    placed = copy.deepcopy(outline)
    tag = tag_of(placed)
    if tag == "rect":
        _set(placed, x=to.left, y=to.top, width=to.width, height=to.height)
    elif tag == "ellipse":
        _set(placed, cx=to.centre.x, cy=to.centre.y, rx=to.width / 2, ry=to.height / 2)
    elif tag == "polygon":
        placed.set("points", _points_written(stretched(corner.x, corner.y) for corner in polygon_corners(placed)))
    elif tag == "path":
        _path_through(placed, stretched)
    else:
        raise Unreadable(f"a <{tag}> where an outline was expected")
    return placed


def _font_size(text: Element) -> float:
    try:
        return float(text.get("font-size") or _DEFAULT_FONT_SIZE)
    except ValueError:
        return _DEFAULT_FONT_SIZE


def drawn_extent(element: Element) -> Extent | None:
    """The rectangle *element* and everything in it is drawn over, or None where it draws nothing."""
    tag = tag_of(element)
    if tag == "g":
        inner = [extent for child in element if (extent := drawn_extent(child)) is not None]
        return Extent(
            min(extent.left for extent in inner), min(extent.top for extent in inner),
            max(extent.right for extent in inner), max(extent.bottom for extent in inner),
        ) if inner else None
    if tag == "text":
        if not (element.text or "").strip():
            return None
        x, y = numbers_of(element, "x", "y")
        width, size = float(element.get("textLength") or 0.0), _font_size(element)
        return Extent(x, y - _ASCENT * size, x + width, y + _DESCENT * size)
    if tag == "image":
        x, y, width, height = numbers_of(element, "x", "y", "width", "height")
        return Extent(x, y, x + width, y + height)
    if tag == "line":
        x1, y1, x2, y2 = numbers_of(element, "x1", "y1", "x2", "y2")
        return Extent(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if tag in ("title", "desc"):
        return None
    return outline_extent(element)
