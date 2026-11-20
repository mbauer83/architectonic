"""What a rendered picture draws: its elements, its boxes and its relations, each where it sits.

These are the values a layout is harvested from and the values the picture checks reason over. They
say what is *on the picture* and nothing about the model: a shape is known by the alias its
declaration gave it, and a caller resolves that to an instance — an entity, or one of its further
occurrences — through the module that owns that join.

`NotReadable` is the other answer a reading can give. A picture whose structure is not the one this
project knows how to read is not partly read: it is named as unread, with what was met.
"""

from __future__ import annotations

from collections.abc import Container, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.domain.diagrams.layout.box_aliases import BoxKind, box_kind
from src.domain.diagrams.layout.geometry import Extent, Point


@dataclass(frozen=True)
class MeasuredWord:
    """One run of text as the renderer set it, with the width the renderer measured for it.

    The width is the renderer's own measurement in its own font, which is the reason to keep it: a
    label can be re-wrapped into a different box without anything here knowing a font metric.
    """

    text: str
    #: Where the run starts: its left edge, on its baseline.
    start: Point
    width: float

    @property
    def end_x(self) -> float:
        return self.start.x + self.width


def text_of(words: tuple[MeasuredWord, ...]) -> str:
    """What a run of words says, read in the order they were set."""
    return " ".join(word.text for word in words)


def extent_across(words: tuple[MeasuredWord, ...]) -> tuple[float, float] | None:
    """The left and right edge of everything *words* set, or None for no words."""
    if not words:
        return None
    return min(word.start.x for word in words), max(word.end_x for word in words)


@dataclass(frozen=True)
class DrawnElement:
    """An element drawn as a shape of its own, with nothing inside it."""

    alias: str
    #: The rectangle its outline occupies — not its glyph, and not its text.
    extent: Extent
    #: The alias of the box it is drawn directly inside, or None when it stands on the canvas.
    inside: str | None
    #: Its label, in the order set. Empty for a shape that carries none, such as a junction.
    words: tuple[MeasuredWord, ...] = ()

    @property
    def label(self) -> str:
        return text_of(self.words)


@dataclass(frozen=True)
class DrawnBox:
    """A box with other shapes inside it: a grouping of any kind, or an element holding its parts."""

    alias: str
    extent: Extent
    inside: str | None
    #: Its title, in the order set.
    words: tuple[MeasuredWord, ...] = ()

    @property
    def label(self) -> str:
        return text_of(self.words)

    def kind(self, *, element_aliases: Container[str]) -> BoxKind:
        """Which of the four kinds of box this is, given the aliases the diagram's instances carry."""
        return box_kind(self.alias, element_aliases=element_aliases)


class MarkShape(StrEnum):
    """How an end decoration is drawn, which decides what its outline's points mean."""

    #: A closed outline through the points, in order.
    POLYGON = "polygon"
    #: An open line through the points, in order.
    LINE = "line"
    #: An ellipse filling the rectangle between the two points.
    ELLIPSE = "ellipse"


@dataclass(frozen=True)
class EndMark:
    """One drawing at a relation's end: an arrowhead, a diamond, a dot."""

    shape: MarkShape
    outline: tuple[Point, ...]
    filled: bool


@dataclass(frozen=True)
class DrawnRelation:
    """One relation as drawn between two shapes.

    *ends* are the two shapes in the order the renderer names them, which is **not** the relation's
    source and target: a picture draws a mark at either end, both or neither, and says nothing of
    which end the relation starts from. The line runs from the first end to the second, and each
    mark is filed under the end it sits at.
    """

    ends: tuple[str, str]
    #: The renderer's name for how the line is drawn — `dependency`, `association`, `extension`.
    line_type: str
    #: The points the line is drawn through. A curve's control points are not among them.
    path: tuple[Point, ...]
    #: The line walked closely enough to ask what it passes: curves are followed, not cut across.
    course: tuple[Point, ...]
    first_marks: tuple[EndMark, ...] = ()
    second_marks: tuple[EndMark, ...] = ()
    #: Every run of text the relation carries, in the order set: its label, and a multiplicity at
    #: either end where one is drawn. Empty when it carries none.
    words: tuple[MeasuredWord, ...] = ()

    @property
    def label(self) -> str:
        return text_of(self.words)


@dataclass(frozen=True)
class RenderedPicture:
    """Everything a rendered picture draws, by alias."""

    canvas: Extent
    elements: Mapping[str, DrawnElement]
    boxes: Mapping[str, DrawnBox]
    relations: tuple[DrawnRelation, ...]

    def extent_of(self, alias: str) -> Extent | None:
        """Where the shape drawn under *alias* sits — element or box — or None when none is."""
        shape = self.elements.get(alias) or self.boxes.get(alias)
        return shape.extent if shape is not None else None

    def label_of(self, alias: str) -> str:
        """What the shape drawn under *alias* is called on the picture; empty for an unlabelled one."""
        shape = self.elements.get(alias) or self.boxes.get(alias)
        return shape.label if shape is not None else ""

    def boxes_around(self, alias: str) -> Iterator[str]:
        """The boxes the shape under *alias* is drawn inside, innermost first."""
        shape = self.elements.get(alias) or self.boxes.get(alias)
        seen: set[str] = set()
        outer = shape.inside if shape is not None else None
        while outer is not None and outer not in seen:
            seen.add(outer)
            yield outer
            outer = self.boxes[outer].inside if outer in self.boxes else None


@dataclass(frozen=True)
class NotReadable:
    """A picture this project does not know how to read, and what it met that told it so.

    Two different situations answer this way, and a caller usually cares which. A sequence chart or
    a natively drawn picture is simply *another kind* of picture: nothing is wrong, and nothing was
    expected. A picture that states the kind this project reads and then holds a structure it does
    not recognise is the external contract having moved — `stated_the_kind_read` says so.
    """

    met: str
    stated_the_kind_read: bool = False
