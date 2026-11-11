"""Draw a sanitised icon SVG to PNG, sized into the icon box.

The drawing itself — resvg in an isolated child process with an empty working directory — is
`rendering.svg_to_png`, shared with diagram types that draw their own SVG. What is the icon's own is
the size: twice the stored box, so the raster codec's resampling has detail to work from. The
sanitiser is the first barrier against a referenced file; the isolated child is the second.
"""

from __future__ import annotations

from src.domain.icons.render_form import STORED_BOX, IconBox
from src.infrastructure.rendering.svg_to_png import RasteriseFailedError, draw_svg_to_png

__all__ = ["RASTER_BOX", "RasteriseFailedError", "rasterise_svg"]

#: Twice the stored size, so the raster codec's resampling has detail to work from.
RASTER_BOX = IconBox(height_px=2 * STORED_BOX.height_px, max_width_px=2 * STORED_BOX.max_width_px)


def rasterise_svg(markup: str, aspect_ratio: float) -> bytes:
    width, height = _edges(aspect_ratio)
    return draw_svg_to_png(markup, width=width, height=height)


def _edges(aspect_ratio: float) -> tuple[int, int]:
    """Width and height for a picture of *aspect_ratio* (width over height), fitted into `RASTER_BOX`."""
    scale = RASTER_BOX.scale_for(aspect_ratio, 1)
    return max(1, round(aspect_ratio * scale)), max(1, round(scale))
