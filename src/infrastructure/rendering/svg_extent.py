"""The canvas an SVG declares: its width and height, from its `viewBox` or else its numeric size.

One reading of the root element's two ways of stating a canvas, for every caller that has to size a
picture of an SVG: an icon upload (which turns it into an aspect ratio and refuses a sliver) and a
diagram type that draws its own SVG (which rasterises it at the size PlantUML would have).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$")


def declared_extent(root_attributes: Mapping[str, str]) -> tuple[float, float] | None:
    """(width, height) from the `viewBox`, else from numeric `width`/`height`; None if neither is stated."""
    return _from_view_box(root_attributes.get("viewBox")) or _from_size(root_attributes)


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
