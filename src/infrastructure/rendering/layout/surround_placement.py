"""Where what PlantUML draws round a diagram — its title, its legend, a caption — goes as the diagram is arranged.

The one rule, read twice: by the composer, which draws a laid-out diagram, and by the editor's canvas, which
asks the layout surround route (`_layout.preview_diagram_surround`) while it arranges. A part keeps to the side or
the middle of the diagram it was drawn at — beside it on the left or the right, else centred across it; below
it, else above it — and the diagram is what its shapes, lines and line labels occupy.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point


def occupied(
    shapes: Iterable[Extent], courses: Iterable[Sequence[Point]], labels: Iterable[Extent],
) -> Extent | None:
    """What shapes, the courses of lines and the lines' labels occupy together; None where they are nothing."""
    around = [*shapes, *(extent for course in courses if (extent := Extent.around(course)) is not None), *labels]
    if not around:
        return None
    return Extent(
        min(extent.left for extent in around), min(extent.top for extent in around),
        max(extent.right for extent in around), max(extent.bottom for extent in around),
    )


def carried_by(part: Extent, was: Extent, now: Extent) -> tuple[float, float]:
    """How far a part drawn at *part* moves as the diagram goes from occupying *was* to occupying *now*."""
    if part.centre.x < was.left:
        dx = now.left - was.left
    elif part.centre.x > was.right:
        dx = now.right - was.right
    else:
        dx = now.centre.x - was.centre.x
    dy = now.bottom - was.bottom if part.centre.y > was.bottom else now.top - was.top
    return dx, dy
