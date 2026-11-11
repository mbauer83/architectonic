"""The shape of the canvas an SVG declares: width over height, from its `viewBox` or its size.

The rasteriser is handed both edges of the picture it draws, so it never derives one from the other
at an unbounded size: a document one unit wide and a hundred thousand tall, rendered to a fixed width,
would otherwise ask for a canvas of billions of pixels. A picture thinner than `MAX_ASPECT` in either
direction is refused here; no icon that shape can be read at 64 px.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.infrastructure.rendering.svg_extent import declared_extent

MAX_ASPECT = 16.0


class UnreadableExtentError(ValueError):
    """The SVG's declared canvas has no positive area, or is too thin to draw as an icon."""


def aspect_ratio(root_attributes: Mapping[str, str]) -> float:
    """Width over height; 1.0 when the document declares neither a `viewBox` nor a numeric size."""
    extent = declared_extent(root_attributes)
    if extent is None:
        return 1.0
    width, height = extent
    if width <= 0 or height <= 0:
        raise UnreadableExtentError("the SVG declares a canvas with no area")
    ratio = width / height
    if not 1 / MAX_ASPECT <= ratio <= MAX_ASPECT:
        raise UnreadableExtentError(f"the SVG is more than {MAX_ASPECT:g} times wider than tall, or taller than wide")
    return ratio

