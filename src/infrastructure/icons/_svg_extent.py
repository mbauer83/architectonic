"""The shape of the canvas an SVG declares: width over height, from its `viewBox` or its size.

The rasteriser is handed both edges of the picture it draws, so it never derives one from the other
at an unbounded size: a document one unit wide and a hundred thousand tall, rendered to a fixed width,
would otherwise ask for a canvas of billions of pixels. A picture thinner than `MAX_ASPECT` in either
direction is refused here; no icon that shape can be read at 64 px.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

MAX_ASPECT = 16.0

_LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$")


class UnreadableExtentError(ValueError):
    """The SVG's declared canvas has no positive area, or is too thin to draw as an icon."""


def aspect_ratio(root_attributes: Mapping[str, str]) -> float:
    """Width over height; 1.0 when the document declares neither a `viewBox` nor a numeric size."""
    extent = _from_view_box(root_attributes.get("viewBox")) or _from_size(root_attributes)
    if extent is None:
        return 1.0
    width, height = extent
    if width <= 0 or height <= 0:
        raise UnreadableExtentError("the SVG declares a canvas with no area")
    ratio = width / height
    if not 1 / MAX_ASPECT <= ratio <= MAX_ASPECT:
        raise UnreadableExtentError(f"the SVG is more than {MAX_ASPECT:g} times wider than tall, or taller than wide")
    return ratio


def _from_view_box(view_box: str | None) -> tuple[float, float] | None:
    parts = (view_box or "").replace(",", " ").split()
    if len(parts) != 4:
        return None
    try:
        return float(parts[2]), float(parts[3])
    except ValueError:
        return None


def _from_size(attributes: Mapping[str, str]) -> tuple[float, float] | None:
    width, height = (_LENGTH_RE.match(attributes.get(edge, "")) for edge in ("width", "height"))
    return (float(width.group(1)), float(height.group(1))) if width and height else None
