"""PlantUML's own picture of a diagram, read, and the first layout written down from it.

What an editor arranges and what a layout is first taken over from is the picture PlantUML draws of
the diagram's body — never a laid-out picture, which is already the layout's. Read here once for the
REST surface and the MCP tools alike, through the one reader of PlantUML's structure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, joined_to_its_picture
from src.application.puml_relation_parsing import without_layout_links
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.diagrams.layout.layout_block import Layout
from src.domain.diagrams.layout.rendered_picture import NotReadable
from src.infrastructure.rendering.layout.first_layout import first_layout
from src.infrastructure.rendering.layout.membership_placement import with_new_members
from src.infrastructure.rendering.layout.plantuml_svg_reader import RenderedDrawing, read_rendered_drawing


class NotDrawn(ValueError):
    """PlantUML drew no picture of a diagram, or drew one the reader cannot read, with why."""


class RendererUnavailable(RuntimeError):
    """This installation cannot run PlantUML at all: a condition of the server, not of the diagram asked about.

    Not a `NotDrawn`, and not a `ValueError`, so no caller reports it as the request's fault.
    """


def plantuml_svg(
    puml_body: str, repo_root: Path, diagram_type: str, restyle_prepared: Callable[[str], str] | None = None,
) -> str:
    """PlantUML's own SVG of *puml_body*, its prepared body restyled where *restyle_prepared* says. Raises
    `NotDrawn` with PlantUML's warnings when there is none, `RendererUnavailable` when PlantUML is absent."""
    from src.application.verification.artifact_verifier_syntax import find_plantuml_jar  # noqa: PLC0415
    from src.infrastructure.rendering.puml_runtime import render_puml_svg  # noqa: PLC0415 - starts the renderer

    if find_plantuml_jar() is None:
        raise RendererUnavailable(
            "PlantUML is not installed for this server (plantuml.jar not found), so no diagram can be drawn "
            "or arranged here. Install it (`get-plantuml`) and retry."
        )
    svg, warnings = render_puml_svg(puml_body, repo_root, diagram_type, restyle_prepared=restyle_prepared)
    if svg is None:
        raise NotDrawn(f"PlantUML could not draw the diagram: {'; '.join(warnings)}")
    return svg


def measure_composition(
    body: str, repo_root: Path, diagram_type: str, restyle_prepared: Callable[[str], str] | None = None,
) -> tuple[str, str]:
    """Return the generated source and the SVG it actually drew, including any necessary rank relaxation.

    Graphviz can crash on nested clusters and return its stack trace as a successful SVG.
    Only that diagnostic retries, without hidden positioning constraints. Save draws the recovered source.
    """
    svg = plantuml_svg(body, repo_root, diagram_type, restyle_prepared)
    if 'data-diagram-type="DESCRIPTION"' not in svg and "An error has occurred" in svg and "plantuml.dot." in svg:
        body = without_layout_links(body)
        svg = plantuml_svg(body, repo_root, diagram_type, restyle_prepared)
    return body, svg


def plantuml_drawing(puml_body: str, repo_root: Path, diagram_type: str) -> RenderedDrawing:
    """PlantUML's picture of *puml_body*, read. Raises `NotDrawn` where it is not drawn or not readable."""
    drawing = read_rendered_drawing(plantuml_svg(puml_body, repo_root, diagram_type))
    if isinstance(drawing, NotReadable):
        raise NotDrawn(f"The diagram's picture cannot be read: {drawing.met}")
    return drawing


def first_layout_of(
    puml_body: str, frontmatter: Mapping[str, object], repo_root: Path, ontology: DeclaresElementKinds
) -> Layout:
    """The layout a diagram starts from when it is first arranged: PlantUML's picture, as drawn."""
    diagram_type = diagram_type_of(frontmatter)
    drawing = plantuml_drawing(puml_body, repo_root, diagram_type)
    return first_layout(drawing.picture, joined_to_its_picture(frontmatter, Layout(), ontology))


def placed_on_its_picture(
    source: str, frontmatter: Mapping[str, object], layout: Layout, *, new: frozenset[str],
    repo_root: Path, ontology: DeclaresElementKinds,
) -> tuple[str, Layout]:
    """*layout* matched to the picture PlantUML draws of *source*, which *frontmatter* states: the instances
    in *new* placed beside their neighbours and every box it does not state fitted round its members.

    Answers the source as drawn too, which is the one to store: drawing may have relaxed its ranking.
    """
    source, svg = measure_composition(source, repo_root, diagram_type_of(frontmatter))
    drawing = read_rendered_drawing(svg)
    if isinstance(drawing, NotReadable):
        raise NotDrawn(f"The diagram's picture cannot be read: {drawing.met}")
    return source, with_new_members(drawing.picture, joined_to_its_picture(frontmatter, layout, ontology), new)
