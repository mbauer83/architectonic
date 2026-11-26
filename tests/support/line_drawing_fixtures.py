"""How a line is drawn along a course, as cases, for `tests/fixtures/layout_geometry/line_drawing.json`.

The composer draws a relation along its course with rounded bends, stops it short of a hollow head and
turns the decorations PlantUML drew to face the course's ends (`relation_drawing`,
`relation_decorations`). The diagram canvas draws its lines the same way while something is dragged, in
TypeScript (`tools/gui/src/domain/layout/canvasLineDrawing.ts`); these cases are what both answer.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.diagrams.layout.geometry import Point
from src.infrastructure.rendering.layout.relation_decorations import heading_at_end, stopping_short
from src.infrastructure.rendering.layout.relation_drawing import rounded_path
from src.infrastructure.rendering.layout.svg_markup import Motion

type Course = Sequence[Sequence[float]]

_COURSES: dict[str, Course] = {
    "a straight run": [[0, 0], [100, 0]],
    "one bend": [[0, 0], [100, 0], [100, 80]],
    "a bend too tight to round": [[0, 0], [1, 0], [1, 1]],
    "a bend rounded only as far as its short run allows": [[0, 0], [8, 0], [8, 50]],
    "a Z": [[0, 0], [50, 0], [50, 40], [120, 40]],
    "a hook at the end": [[0, 0], [100, 0], [100, 80], [100, 78]],
    "a run going nowhere": [[5, 5], [5, 5]],
}

_GAPS = [(0.0, 10.0), (12.0, 0.0), (30.0, 30.0)]

#: Frames decorations were drawn in, by where they touched and which way they pointed.
_FRAMES = [([10.0, 20.0], [1.0, 0.0]), ([40.0, 5.0], [0.0, -1.0]), ([7.5, 7.5], [0.6, 0.8])]


def _points(course: Course) -> tuple[Point, ...]:
    return tuple(Point(float(x), float(y)) for x, y in course)


def _written(points: Sequence[Point]) -> list[list[float]]:
    return [[point.x, point.y] for point in points]


def _decoration(at: list[float], heading: list[float], course: tuple[Point, ...]) -> dict[str, object]:
    motion = Motion.facing(Point(*at), (heading[0], heading[1]), course[-1], heading_at_end(course))
    return {"at": at, "heading": heading, "to": [motion.to.x, motion.to.y], "degrees": motion.degrees}


def build_line_drawing() -> dict[str, object]:
    cases = []
    for name, raw in _COURSES.items():
        course = _points(raw)
        moving = len({(point.x, point.y) for point in course}) > 1
        cases.append({
            "name": name,
            "course": _written(course),
            "path": rounded_path(course),
            "heading": list(heading_at_end(course)),
            "short": [
                {"gaps": list(gaps), "course": _written(stopping_short(course, *gaps))} for gaps in _GAPS
            ] if moving else [],
            "decorations": [_decoration(at, heading, course) for at, heading in _FRAMES] if moving else [],
        })
    return {"cases": cases}
