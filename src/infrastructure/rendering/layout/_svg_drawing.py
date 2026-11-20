"""The drawing primitives inside one group of a rendered picture: an outline's extent, a run of text.

Each reading either answers in full or raises `Unreadable` naming what it met. Nothing here returns
a default for a missing coordinate: a shape with no `x` is not a shape at the origin.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from xml.etree.ElementTree import Element  # the type only; input is parsed by defusedxml

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import EndMark, MarkShape, MeasuredWord
from src.infrastructure.rendering.layout.svg_path_data import UnreadablePath, read_path

SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: The elements PlantUML draws an outline, a glyph or a decoration with.
OUTLINE_TAGS = frozenset({"rect", "path", "polygon", "ellipse"})


class Unreadable(Exception):
    """A structure this reader does not recognise. Carries what was met, in a reviewer's words."""

    def __init__(self, met: str) -> None:
        super().__init__(met)
        self.met = met


def tag_of(element: Element) -> str:
    """The element's name without its namespace; an element outside SVG's namespace is unreadable."""
    namespace, _, name = element.tag.rpartition("}")
    if namespace != "{" + SVG_NAMESPACE:
        raise Unreadable(f"an element outside the SVG namespace: {element.tag!r}")
    return name


def numbers_of(element: Element, *names: str) -> tuple[float, ...]:
    """The named attributes as numbers, all of them or `Unreadable`."""
    values: list[float] = []
    for name in names:
        text = element.get(name)
        if text is None:
            raise Unreadable(f"a <{tag_of(element)}> with no {name!r}")
        try:
            values.append(float(text))
        except ValueError:
            raise Unreadable(f"a <{tag_of(element)}> whose {name!r} is {text!r}, not a number") from None
    if not all(math.isfinite(value) for value in values):
        raise Unreadable(f"a <{tag_of(element)}> with a coordinate that is not finite")
    return tuple(values)


def polygon_corners(element: Element) -> tuple[Point, ...]:
    values = (element.get("points") or "").replace(",", " ").split()
    try:
        numbers = [float(value) for value in values]
    except ValueError:
        raise Unreadable(f"a <polygon> whose points are {element.get('points')!r}") from None
    if not numbers or len(numbers) % 2:
        raise Unreadable(f"a <polygon> with {len(numbers)} coordinates")
    return tuple(Point(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2))


def path_course(element: Element) -> tuple[tuple[Point, ...], tuple[Point, ...]]:
    """A `<path>`'s points and its walked course."""
    try:
        reading = read_path(element.get("d") or "")
    except UnreadablePath as exc:
        raise Unreadable(str(exc)) from None
    return reading.through, reading.course


def outline_extent(element: Element) -> Extent:
    """The rectangle one outline element occupies."""
    tag = tag_of(element)
    if tag == "rect":
        x, y, width, height = numbers_of(element, "x", "y", "width", "height")
        return Extent(x, y, x + width, y + height)
    if tag == "ellipse":
        cx, cy, rx, ry = numbers_of(element, "cx", "cy", "rx", "ry")
        return Extent(cx - rx, cy - ry, cx + rx, cy + ry)
    points = polygon_corners(element) if tag == "polygon" else path_course(element)[1] if tag == "path" else ()
    extent = Extent.around(points)
    if extent is None:
        raise Unreadable(f"a <{tag}> where an outline was expected")
    return extent


def end_mark(element: Element) -> EndMark:
    """One decoration at a relation's end, as drawn."""
    tag = tag_of(element)
    filled = (element.get("fill") or "none") != "none"
    if tag == "polygon":
        return EndMark(MarkShape.POLYGON, polygon_corners(element), filled)
    if tag == "path":
        return EndMark(MarkShape.LINE, path_course(element)[0], filled)
    if tag == "ellipse":
        extent = outline_extent(element)
        return EndMark(
            MarkShape.ELLIPSE, (Point(extent.left, extent.top), Point(extent.right, extent.bottom)), filled
        )
    if tag == "line":
        x1, y1, x2, y2 = numbers_of(element, "x1", "y1", "x2", "y2")
        return EndMark(MarkShape.LINE, (Point(x1, y1), Point(x2, y2)), filled=False)
    raise Unreadable(f"a <{tag}> among a relation's decorations")


def measured_words(texts: Iterable[Element]) -> tuple[MeasuredWord, ...]:
    """The runs of text among *texts* that say something, each with its measured width.

    PlantUML sets every word as its own `<text>` and every space between two as another; the spaces
    are dropped, since each word carries where it starts. A run with no measured width is
    unreadable rather than zero wide: the width is the whole of what this is read for.
    """
    words: list[MeasuredWord] = []
    for text in texts:
        if len(text):
            raise Unreadable("a <text> with elements inside it")
        said = (text.text or "").strip()
        if not said:
            continue
        x, y, width = numbers_of(text, "x", "y", "textLength")
        words.append(MeasuredWord(text=said, start=Point(x, y), width=width))
    return tuple(words)
