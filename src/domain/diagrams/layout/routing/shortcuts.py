"""Remove a pair of bends where extending a straight run reaches the fourth run safely."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.diagrams.layout.geometry import Point, course_length
from src.domain.diagrams.layout.routing.lines import Lines, Stubs
from src.domain.diagrams.layout.routing.scene import PARALLEL_SEPARATION, Connector, RoutedConnector, run_for
from src.domain.diagrams.layout.routing.visibility import Passage, Visibility


def _clear_leg(
    start: Point, old: Point, corner: Point, passage: Passage, minimum: float, occupied: Lines, *, arriving: bool,
) -> bool:
    """A shortened leg stays on the original line. Only a new extension needs checking."""
    dx, dy = old.x - start.x, old.y - start.y
    if dx * (corner.x - start.x) + dy * (corner.y - start.y) <= 0 or start.distance_to(corner) < minimum:
        return False
    if start.distance_to(corner) <= start.distance_to(old):
        return True
    a, b = (corner, old) if arriving else (old, corner)
    return not passage.step_blocked(a, b) and not occupied.near(a, b, PARALLEL_SEPARATION)


def shorten(
    courses: dict[str, list[Point]], connectors: Sequence[Connector], visibility: Visibility,
    unseparated: Sequence[tuple[str, str]],
) -> None:
    unresolved = {key for pair in unseparated for key in pair}
    occupied = Lines()
    for course in (*courses.values(), *visibility.scene.fixed_lines):
        for a, b in zip(course, course[1:], strict=False):
            occupied.add(a, b)
    for connector in connectors:
        key = connector.key
        if key in unresolved or len(course := courses.get(key, [])) < 5:
            continue
        passage = visibility.passage((connector.source, connector.target))
        i = 0
        while i + 4 < len(course):
            a, b, _, d, e = course[i:i + 5]
            corner = Point(e.x, a.y) if a.y == b.y else Point(a.x, e.y)
            source = run_for(connector.decorated[0]) if i == 0 else 1.0
            target = run_for(connector.decorated[1]) if i + 5 == len(course) else 1.0
            if _clear_leg(a, b, corner, passage, source, occupied, arriving=False) and _clear_leg(
                e, d, corner, passage, target, occupied, arriving=True,
            ):
                course[i + 1:i + 4] = [corner]
                occupied.add(a, corner)
                occupied.add(corner, e)
            else:
                i += 1

def improves_detour(before: RoutedConnector, alternative: RoutedConnector, stubs: Stubs) -> bool:
    """A different port must save bends, fit the reserved end runs and cost no extra length."""
    course = alternative.course
    return (len(course) < len(before.course) and course_length(course) <= course_length(before.course)
            and not any(stubs.along(a, b, before.key) for a, b in zip(course, course[1:], strict=False)))
