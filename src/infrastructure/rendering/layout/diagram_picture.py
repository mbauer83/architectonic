"""PlantUML's own picture of a diagram, read, and the first layout written down from it.

What an editor arranges and what a layout is first taken over from is the picture PlantUML draws of
the diagram's body — never a laid-out picture, which is already the layout's. Read here once for the
REST surface and the MCP tools alike, through the one reader of PlantUML's structure.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, joined_to_its_picture
from src.domain.diagrams.layout.layout_block import Layout
from src.domain.diagrams.layout.rendered_picture import NotReadable
from src.infrastructure.rendering.layout.first_layout import first_layout
from src.infrastructure.rendering.layout.plantuml_svg_reader import RenderedDrawing, read_rendered_drawing


class NotDrawn(ValueError):
    """PlantUML drew no picture of a diagram, or drew one the reader cannot read, with why."""


def plantuml_svg(puml_body: str, repo_root: Path, diagram_type: str) -> str:
    """PlantUML's own SVG of *puml_body*. Raises `NotDrawn` with PlantUML's warnings when there is none."""
    from src.infrastructure.rendering.puml_runtime import render_puml_svg  # noqa: PLC0415 - starts the renderer

    svg, warnings = render_puml_svg(puml_body, repo_root, diagram_type)
    if svg is None:
        raise NotDrawn(f"PlantUML could not draw the diagram: {'; '.join(warnings)}")
    return svg


def plantuml_drawing(puml_body: str, repo_root: Path, diagram_type: str) -> RenderedDrawing:
    """PlantUML's picture of *puml_body*, read. Raises `NotDrawn` where it is not drawn or not readable."""
    drawing = read_rendered_drawing(plantuml_svg(puml_body, repo_root, diagram_type))
    if isinstance(drawing, NotReadable):
        raise NotDrawn(f"The diagram's picture cannot be read: {drawing.met}")
    return drawing


def first_layout_of(
    puml_body: str, frontmatter: Mapping[str, object], repo_root: Path, ontology: DeclaresElementKinds
) -> Layout:
    """The layout a diagram starts from when it is first arranged: PlantUML's picture, widened."""
    diagram_type = str(frontmatter.get("diagram-type", "archimate"))
    drawing = plantuml_drawing(puml_body, repo_root, diagram_type)
    return first_layout(drawing.picture, joined_to_its_picture(frontmatter, Layout(), ontology))
