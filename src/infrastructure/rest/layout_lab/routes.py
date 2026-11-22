"""The layout lab's routes: mounted only when the lab is switched on, and never part of the REST contract.

**Why these carry no route-policy row.** The manifest classifies the modelled REST contract — what the
published OpenAPI document states, what the generated client types are built from, what the timeout
policy and the write authorization govern — and its fitness functions hold the served document equal to
it. The lab is a developer's bench beside the product, as the health probe, the MCP mounts and the
documentation views are, and it is treated as they are: outside `/api`, `include_in_schema=False`,
no row. That is what keeps a lab switched off from changing anything: the served document, the
generated types and every gate are the same whether this module exists or not, and with the lab on
the document is still the same, because nothing here is in it.

**Nothing is written.** One write-shaped call composes a picture from a layout the caller holds;
nothing it needs is kept. The picture the lab arranges and the shapes it resizes are the product's
own routes (`routers/diagrams/_layout`), which the diagram canvas uses too: the lab is a bench over the
same canvas, not a second one.
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
from src.infrastructure.rendering.layout.composer import NotComposed, compose
from src.infrastructure.rendering.layout.diagram_picture import NotDrawn, plantuml_svg
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s

#: Where the lab answers: beside `/api`, never under it.
LAB_PREFIX = "/lab/layout"

#: Nothing the lab answers is kept by a browser: every answer is of one moment's layout.
_NOT_KEPT = {"Cache-Control": "no-store"}


def _drawn_by_plantuml(artifact_id: str) -> tuple[str, dict[str, object]]:
    """PlantUML's own picture of a stored diagram, and the frontmatter it was drawn from."""
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    repo_root = s.maybe_engagement_root()
    record = s.get_repo().get_diagram(artifact_id)
    if repo_root is None or record is None or not Path(record.path).exists():
        raise HTTPException(404, f"Diagram '{artifact_id}' not found")
    parsed = parse_diagram_file(Path(record.path))
    try:
        svg = plantuml_svg(parsed.puml_body, repo_root, record.diagram_type)
    except NotDrawn as refusal:
        raise HTTPException(500, f"{artifact_id}: {refusal}") from refusal
    return svg, dict(parsed.frontmatter)


def read_lab_status() -> JSONResponse:
    """Answers only while the lab is on, so the GUI shows its menu entry exactly then."""
    return JSONResponse({"enabled": True}, headers=_NOT_KEPT)


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


def install_layout_lab(app: FastAPI) -> None:
    """Mount the lab's routes on *app* when the lab is switched on; otherwise do nothing at all."""
    if not layout_lab_enabled():
        return
    app.add_api_route(LAB_PREFIX, read_lab_status, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        f"{LAB_PREFIX}/diagrams/{{artifact_id}}/picture", compose_lab_picture, methods=["POST"],
        include_in_schema=False,
    )
