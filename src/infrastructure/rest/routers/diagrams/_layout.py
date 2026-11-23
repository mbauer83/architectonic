"""Arranging a diagram: the picture an editor arranges, shapes drawn at a new size, and a layout patch.

The read and the drawing write nothing. The patch is the one write: entries of the layout block,
applied to the stored layout — or, on a diagram PlantUML still arranges, to the first layout taken
over from its picture — and written through the diagram edit, so it is refused and verified as any
layout is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.application.modeling.diagram_identities import alias_by_instance
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, MalformedLayout
from src.domain.diagrams.layout.layout_patch import LayoutConflict
from src.domain.diagrams.layout.rendered_picture import NotReadable
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.diagram_picture import (
    NotDrawn,
    first_layout_of,
    measure_composition,
    plantuml_svg,
)
from src.infrastructure.rest.contracts.diagram_layout_editing import (
    DiagramLayoutGeometryResponse,
    DiagramLayoutPatchResponse,
    ShapeDrawingsResponse,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_DIAGRAMS,
    WRITE_RESPONSES,
)
from src.infrastructure.rest.routers.diagrams._composition import render_composition
from src.infrastructure.rest.routers.diagrams._geometry_proposals import GeometryPreviewBody
from src.infrastructure.rest.routers.diagrams._layout_drawing import reshaped
from src.infrastructure.rest.routers.diagrams._layout_geometry import diagram_geometry
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.parse_existing import ParsedDiagram, parse_diagram_file

router = APIRouter()

Catalogs = Annotated[RuntimeCatalogs, Depends(runtime_catalogs_dependency)]


class DrawingNodeBody(BaseModel):
    """A piece of PlantUML's drawing as the geometry read handed it over, sent back to be drawn anew."""

    model_config = ConfigDict(extra="forbid")

    tag: str
    attributes: dict[str, str]
    text: str | None = None
    children: list[DrawingNodeBody] = []


class ExtentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float


class ShapeToDraw(BaseModel):
    """A shape an editor resized: PlantUML's drawing of it, where that was drawn, and where it is to go."""

    model_config = ConfigDict(extra="forbid")

    drawing: DrawingNodeBody
    box: bool
    drawn: ExtentBody
    to: ExtentBody


class DrawShapesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shapes: list[ShapeToDraw]


class PatchLayoutBody(BaseModel):
    """Entries of the layout block by section (``elements``, ``boxes``, ``relations``, ``z``) and key.

    Each entry is ``null`` to remove it, or ``{value, based_on?}``: what it becomes (``null`` removes
    it) and what the caller read it as (``null`` for absent). A ``based_on`` that no longer holds is
    a conflict, and nothing is written.
    """

    model_config = ConfigDict(extra="forbid")

    patch: dict[str, dict[str, Any]]
    dry_run: bool = True


def _stored_diagram(artifact_id: str) -> ParsedDiagram:
    record = s.get_repo().get_diagram(artifact_id)
    if record is None or not Path(record.path).exists():
        raise HTTPException(404, f"Diagram '{artifact_id}' not found")
    return parse_diagram_file(Path(record.path))


def _repo_root() -> Path:
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(404, "No engagement repository is open")
    return root


@router.get(
    "/api/diagrams/{artifact_id}/layout/geometry", tags=[TAG_DIAGRAMS],
    summary="Read the picture a diagram is arranged on", response_model=DiagramLayoutGeometryResponse,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def read_diagram_layout_geometry(artifact_id: str, catalogs: Catalogs) -> dict[str, object]:
    parsed = _stored_diagram(artifact_id)
    frontmatter = dict(parsed.frontmatter)
    return _geometry_response(parsed.puml_body, artifact_id, frontmatter, catalogs)


def _geometry_response(
    puml: str, artifact_id: str, frontmatter: dict[str, Any], catalogs: RuntimeCatalogs,
    *, generated: bool = False, arrangement: dict[str, Any] | None = None, previous: frozenset[str] = frozenset(),
) -> dict[str, object]:
    diagram_type = str(frontmatter.get("diagram-type", "archimate"))
    try:
        if generated:
            _, svg = measure_composition(puml, _repo_root(), diagram_type)
        else:
            svg = plantuml_svg(puml, _repo_root(), diagram_type)
    except NotDrawn as refusal:
        raise HTTPException(422, str(refusal)) from refusal
    try:
        geometry = diagram_geometry(svg, frontmatter, catalogs.ontology, arrangement=arrangement, previous=previous)
    except MalformedLayout as exc:
        raise HTTPException(422, str(exc)) from exc
    if isinstance(geometry, NotReadable):
        raise HTTPException(422, f"This diagram's picture cannot be arranged: {geometry.met}")
    stored = frontmatter.get(LAYOUT_KEY)
    return {
        "artifact_id": str(frontmatter.get("artifact-id", artifact_id)),
        "name": str(frontmatter.get("name") or artifact_id),
        **({"layout": stored} if isinstance(stored, dict) and stored else {}),
        **geometry,
    }


@router.post(
    "/api/diagrams/{artifact_id}/layout/geometry/preview", tags=[TAG_DIAGRAMS],
    summary="Draw an unsaved diagram composition with layout keys", response_model=DiagramLayoutGeometryResponse,
    response_model_exclude_none=True, responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def preview_diagram_layout_geometry(
    artifact_id: str, body: GeometryPreviewBody, catalogs: Catalogs,
) -> dict[str, object]:
    parsed = _stored_diagram(artifact_id)
    repo = s.get_repo()
    try:
        elements, relations = body.proposals(catalogs, repo)
        composed = render_composition(
            body, repo=repo, repo_root=_repo_root(), proposed_entities=elements, proposed_connections=relations,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _geometry_response(composed.puml, artifact_id, {
        **parsed.frontmatter, **composed.statements(body),
    }, catalogs, generated=True, arrangement=body.arrangement,
        previous=frozenset(alias_by_instance(parsed.frontmatter)))


@router.post(
    "/api/diagrams/{artifact_id}/layout/preview", tags=[TAG_DIAGRAMS],
    summary="Draw resized shapes of a diagram, writing nothing", response_model=ShapeDrawingsResponse,
    response_model_exclude_none=True,
    # As the diagram preview declares them: a write-shaped operation that mutates nothing still passes
    # through the workspace gate and authorization every POST does, and can be refused by either.
    responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def preview_diagram_layout_shapes(artifact_id: str, body: DrawShapesBody) -> dict[str, object]:
    """Each shape drawn by the composer at its new size. Needs nothing of the diagram but its address:
    the drawing, where it was drawn and where it goes all arrive in the request."""
    _ = artifact_id
    try:
        return {"drawings": [reshaped(shape.model_dump()) for shape in body.shapes]}
    except Unreadable as unreadable:
        raise HTTPException(422, f"This shape cannot be drawn: {unreadable.met}") from unreadable


@router.patch(
    "/api/diagrams/{artifact_id}/layout", tags=[TAG_DIAGRAMS],
    summary="Change entries of a diagram's layout", response_model=DiagramLayoutPatchResponse,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def patch_diagram_layout_gui(artifact_id: str, body: PatchLayoutBody, catalogs: Catalogs) -> dict[str, object]:
    from src.infrastructure.write.artifact_write.diagram_layout_patch import patch_diagram_layout  # noqa: PLC0415

    repo_root, _, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            "diagrams_patch_diagram_layout",
            patch_diagram_layout,
            repo_root=repo_root, verifier=verifier, clear_repo_caches=s.clear_caches,
            assert_write_root=assert_engagement_write_root, artifact_id=artifact_id, patch=body.patch,
            first_layout=lambda body_text, frontmatter: first_layout_of(
                body_text, frontmatter, repo_root, catalogs.ontology
            ),
            dry_run=body.dry_run,
        )
    except LayoutConflict as conflict:
        raise HTTPException(409, str(conflict)) from conflict
    except NotDrawn as refusal:
        raise HTTPException(422, str(refusal)) from refusal
    except (MalformedLayout, ValueError) as refusal:
        raise HTTPException(400, str(refusal)) from refusal
    write = result.write
    return {
        "artifact_id": write.artifact_id, "wrote": write.wrote, "warnings": list(write.warnings),
        "errors": write.error_messages, "layout": result.layout,
    }
