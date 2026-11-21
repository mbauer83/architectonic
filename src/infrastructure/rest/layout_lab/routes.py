"""The layout lab's routes: mounted only when the lab is switched on, and never part of the REST contract.

**Why these carry no route-policy row.** The manifest classifies the modelled REST contract — what the
published OpenAPI document states, what the generated client types are built from, what the timeout
policy and the write authorization govern — and its fitness functions hold the served document equal to
it. The lab is a developer's bench beside the product, as the health probe, the MCP mounts and the
documentation views are, and it is treated as they are: outside `/api`, `include_in_schema=False`,
no row. That is what keeps a lab switched off from changing anything: the served document, the
generated types and every gate are the same whether this module exists or not, and with the lab on
the document is still the same, because nothing here is in it.

**Nothing is written.** One read gives the geometry of PlantUML's picture of a diagram; one
write-shaped call composes a picture from a layout the caller holds; another draws shapes the caller
resized, from the drawing that read gave it. None touches the repository: what each needs arrives in
the request and goes nowhere else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response

from src.application.modeling.diagram_layout_statement import joined_to_its_picture
from src.application.runtime_catalogs import RuntimeCatalogs
from src.config.settings import layout_lab_enabled
from src.domain.diagrams.layout.layout_block import MalformedLayout, read_layout
from src.domain.diagrams.layout.rendered_picture import NotReadable
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.composer import NotComposed, compose
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.layout_lab.drawing import reshaped
from src.infrastructure.rest.layout_lab.geometry import diagram_geometry
from src.infrastructure.rest.routers import state as s

#: Where the lab answers: beside `/api`, never under it.
LAB_PREFIX = "/lab/layout"

#: Nothing the lab answers is kept by a browser: every answer is of one moment's layout.
_NOT_KEPT = {"Cache-Control": "no-store"}


def _drawn_by_plantuml(artifact_id: str) -> tuple[str, dict[str, object]]:
    """PlantUML's own picture of a stored diagram, and the frontmatter it was drawn from."""
    from src.infrastructure.rendering.puml_runtime import render_puml_svg  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    repo_root = s.maybe_engagement_root()
    record = s.get_repo().get_diagram(artifact_id)
    if repo_root is None or record is None or not Path(record.path).exists():
        raise HTTPException(404, f"Diagram '{artifact_id}' not found")
    parsed = parse_diagram_file(Path(record.path))
    svg, warnings = render_puml_svg(parsed.puml_body, repo_root, record.diagram_type)
    if svg is None:
        raise HTTPException(500, f"PlantUML could not draw '{artifact_id}': {'; '.join(warnings)}")
    return svg, dict(parsed.frontmatter)


def read_lab_status() -> JSONResponse:
    """Answers only while the lab is on, so the GUI shows its menu entry exactly then."""
    return JSONResponse({"enabled": True}, headers=_NOT_KEPT)


def read_lab_geometry(
    artifact_id: str, catalogs: Annotated[RuntimeCatalogs, Depends(runtime_catalogs_dependency)]
) -> JSONResponse:
    svg, frontmatter = _drawn_by_plantuml(artifact_id)
    geometry = diagram_geometry(svg, frontmatter, catalogs.ontology)
    if isinstance(geometry, NotReadable):
        raise HTTPException(422, f"The lab cannot read this diagram's picture: {geometry.met}")
    return JSONResponse(
        {"artifact_id": artifact_id, "name": str(frontmatter.get("name") or artifact_id), **geometry},
        headers=_NOT_KEPT,
    )


def compose_lab_picture(
    artifact_id: str,
    layout: Annotated[dict[str, object], Body(embed=True)],
    catalogs: Annotated[RuntimeCatalogs, Depends(runtime_catalogs_dependency)],
) -> Response:
    try:
        stated = read_layout(layout)
    except MalformedLayout as refusal:
        raise HTTPException(422, str(refusal)) from refusal
    svg, frontmatter = _drawn_by_plantuml(artifact_id)
    composed = compose(svg, joined_to_its_picture(frontmatter, stated, catalogs.ontology))
    if isinstance(composed, NotComposed):
        raise HTTPException(422, f"The layout could not be composed: {composed.met}")
    return Response(content=composed, media_type="image/svg+xml", headers=_NOT_KEPT)


def reshape_lab_shapes(shapes: Annotated[list[dict[str, object]], Body(embed=True)]) -> JSONResponse:
    """Each shape's drawing at the size it was given, drawn by the composer. Needs no diagram: the
    drawing, where it was drawn and where it goes all arrive in the request."""
    try:
        drawings = [reshaped(shape) for shape in shapes]
    except Unreadable as unreadable:
        raise HTTPException(422, f"The lab cannot draw this shape: {unreadable.met}") from unreadable
    return JSONResponse({"drawings": drawings}, headers=_NOT_KEPT)


def install_layout_lab(app: FastAPI) -> None:
    """Mount the lab's routes on *app* when the lab is switched on; otherwise do nothing at all."""
    if not layout_lab_enabled():
        return
    app.add_api_route(LAB_PREFIX, read_lab_status, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        f"{LAB_PREFIX}/diagrams/{{artifact_id}}/geometry", read_lab_geometry, methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        f"{LAB_PREFIX}/diagrams/{{artifact_id}}/picture", compose_lab_picture, methods=["POST"],
        include_in_schema=False,
    )
    app.add_api_route(f"{LAB_PREFIX}/shapes", reshape_lab_shapes, methods=["POST"], include_in_schema=False)
