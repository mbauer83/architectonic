"""The one step every image path takes after PlantUML has drawn a diagram: draw it from its layout, if it states one.

PlantUML stays the notation. A diagram without a layout is PlantUML's picture byte for byte, and a
diagram with one is that picture composed again from the layout (`layout.composer`). Every path that
produces an image of a stored diagram — the stored SVG and PNG, the lensed view, the download —
asks here, so none of them can draw a laid-out diagram some other way, or forget to.

A PNG of a laid-out diagram is rasterised from the composed SVG, at the density PlantUML's own PNG
would have, since PlantUML never draws the composed picture. A diagram type that draws its own SVG
is rasterised the same way, and for the same reason.

A picture that cannot be composed is drawn as PlantUML drew it, with a warning saying why: a diagram
drawn in its automatic arrangement is still a true picture of it.
"""

from __future__ import annotations

from pathlib import Path

from defusedxml.ElementTree import fromstring

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, laid_out_diagram
from src.config.settings import plantuml_limit_size, render_dpi
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.infrastructure.rendering.layout.composer import NotComposed, compose
from src.infrastructure.rendering.svg_extent import declared_extent
from src.infrastructure.rendering.svg_to_png import draw_svg_to_png

#: An opaque page, as every PlantUML PNG has: a transparent diagram PNG shows its black text on black in
#: any dark viewer, and the GSN legend disappeared that way.
PNG_BACKGROUND = "#FFFFFF"

#: The density PlantUML's SVG is drawn at.
_SVG_DPI = 96


class NoCanvasSizeError(ValueError):
    """An SVG that states no size to rasterise it at."""


def stored_layout(diagram_path: Path, ontology: DeclaresElementKinds) -> LaidOutDiagram | None:
    """What the diagram stored at *diagram_path* is drawn from, or None for PlantUML's own arrangement."""
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    return laid_out_diagram(parse_diagram_file(diagram_path).frontmatter, ontology)


def drawn_from_layout(plantuml_svg: str, laid_out: LaidOutDiagram | None) -> tuple[str, list[str]]:
    """*plantuml_svg* composed from *laid_out*, or unchanged where there is none; and any warning."""
    if laid_out is None:
        return plantuml_svg, []
    composed = compose(plantuml_svg, laid_out)
    if isinstance(composed, NotComposed):
        return plantuml_svg, [f"Drawn in its automatic arrangement: its layout could not be applied ({composed.met})"]
    return composed, []


def png_like_plantuml(svg: str) -> bytes:
    """*svg* rasterised at the size PlantUML's PNG of it would have. Raises `RasteriseFailedError`.

    PlantUML renders at `render_dpi()` over its 96-dpi base (measured: PNG / SVG = 1.56 at 150 dpi),
    so the same scale gives the same picture density; the canvas is capped at PlantUML's own size limit.
    """
    extent = declared_extent(dict(fromstring(svg).attrib))
    if extent is None or extent[0] <= 0 or extent[1] <= 0:
        raise NoCanvasSizeError("the diagram's SVG declares no canvas size")
    scale, limit = render_dpi() / _SVG_DPI, plantuml_limit_size()
    width, height = (min(limit, max(1, round(edge * scale))) for edge in extent)
    return draw_svg_to_png(svg, width=width, height=height, background=PNG_BACKGROUND)


def drawn_for_source(plantuml_svg: str, loc: str) -> tuple[str, bool]:
    """What is drawn for the diagram stored at *loc*, given PlantUML's picture of it, and whether it is laid out.

    For the verifier, which judges the picture a reader sees: a laid-out diagram's is the composed one.
    A source that cannot be read as a diagram, or whose layout cannot be applied, is PlantUML's.
    """
    from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415

    try:
        laid_out = stored_layout(Path(loc), process_runtime_catalogs().ontology)
    except (OSError, UnicodeDecodeError, ValueError):
        return plantuml_svg, False
    if laid_out is None:
        return plantuml_svg, False
    composed = compose(plantuml_svg, laid_out)
    return (plantuml_svg, False) if isinstance(composed, NotComposed) else (composed, True)
