"""An SVG path's `d` attribute, read as the points it is drawn through and the course it follows.

Only what PlantUML writes: absolute commands, `M`, `L`, `C`, `Q`, `A` and `Z`. Anything else — a
relative command, a shorthand curve — raises `UnreadablePath` rather than being approximated, because
the caller's contract is that a picture is read whole or named as unread.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from src.domain.diagrams.layout.geometry import Point

#: How many straight steps stand in for one curve when its course is walked. PlantUML's curves are
#: gentle; eight steps keep the walked course within a pixel of the drawn one at these sizes.
_STEPS_PER_CURVE = 8

_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

#: How many numbers each command takes per repetition.
_ARITY = {"M": 2, "L": 2, "C": 6, "Q": 4, "A": 7, "Z": 0}


class UnreadablePath(ValueError):
    """A path this module does not know how to follow."""


@dataclass(frozen=True)
class PathReading:
    """A path as the points it is drawn through, and as a course close enough to walk."""

    #: Where the path starts and where each of its pieces ends. No control points.
    through: tuple[Point, ...]
    #: The same path with every curve followed in short straight steps.
    course: tuple[Point, ...]


def _bezier(points: Sequence[Point], t: float) -> Point:
    """De Casteljau: the point a fraction *t* along the curve these control points describe."""
    if len(points) == 1:
        return points[0]
    return _bezier(
        [Point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) for a, b in pairwise(points)], t
    )


def _pieces(d: str) -> list[tuple[str, tuple[float, ...]]]:
    """The path as (command, numbers) pieces, one per repetition of a command."""
    tokens = _TOKEN.findall(d)
    if "".join(tokens) != re.sub(r"[\s,]+", "", d):
        raise UnreadablePath(f"path data that is not commands and numbers: {d[:60]!r}")
    pieces: list[tuple[str, tuple[float, ...]]] = []
    position = 0
    while position < len(tokens):
        command = tokens[position]
        arity = _ARITY.get(command)
        if arity is None:
            raise UnreadablePath(f"the path command {command!r}")
        position += 1
        if arity == 0:
            pieces.append((command, ()))
            continue
        numbers: list[float] = []
        while position < len(tokens) and not tokens[position].isalpha():
            numbers.append(float(tokens[position]))
            position += 1
        if not numbers or len(numbers) % arity:
            raise UnreadablePath(f"{len(numbers)} numbers after the path command {command!r}")
        pieces.extend(
            (command, tuple(numbers[start : start + arity])) for start in range(0, len(numbers), arity)
        )
    return pieces


def read_path(d: str) -> PathReading:
    """The points *d* is drawn through, and its course. Raises `UnreadablePath`."""
    through: list[Point] = []
    course: list[Point] = []
    for command, numbers in _pieces(d):
        if command == "Z":
            if through:
                course.append(through[0])
            continue
        end = Point(numbers[-2], numbers[-1])
        if command in ("C", "Q"):
            if not through:
                raise UnreadablePath("a curve before any starting point")
            controls = (
                through[-1],
                *(Point(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)),
            )
            course.extend(
                _bezier(controls, step / _STEPS_PER_CURVE) for step in range(1, _STEPS_PER_CURVE)
            )
        # An arc is walked as its chord. PlantUML draws arcs only in glyphs and rounded outlines,
        # where the chord is a few pixels; no relation's line is an arc.
        through.append(end)
        course.append(end)
    if not through:
        raise UnreadablePath("a path that draws nothing")
    return PathReading(through=tuple(through), course=tuple(course))
