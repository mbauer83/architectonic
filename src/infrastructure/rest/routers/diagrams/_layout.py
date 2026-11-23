"""Arranging a diagram: the picture an editor arranges, shapes drawn at a new size, and a layout patch.

The read and the drawing write nothing. The patch is the one write: entries of the layout block,
applied to the stored layout — or, on a diagram PlantUML still arranges, to the first layout taken
over from its picture — and written through the diagram edit, so it is refused and verified as any
layout is.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.application.modeling.diagram_identities import alias_by_instance
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.diagrams.layout.layout_block import MalformedLayout
from src.domain.diagrams.layout.layout_patch import LayoutConflict
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.diagram_geometry import geometry_response, intents_patch, stored_geometry
from src.infrastructure.rendering.layout.diagram_picture import NotDrawn, first_layout_of
from src.infrastructure.rendering.layout.drawing_wire import reshaped
from src.infrastructure.rest.contracts.diagram_layout_editing import (
    DiagramLayoutGeometryResponse,
    DiagramLayoutIntentsResponse,
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
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.parse_existing import ParsedDiagram, parse_diagram_file

if TYPE_CHECKING:
    from src.infrastructure.write.artifact_write.diagram_layout_patch import PatchOf

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
    return _geometry(lambda: stored_geometry(parsed, artifact_id, _repo_root(), catalogs.ontology))


def _geometry(read: Callable[[], dict[str, object]]) -> dict[str, object]:
    """A geometry read, refused as 422 where the picture cannot be drawn or the layout cannot be read."""
    try:
        return read()
    except ValueError as refusal:  # MalformedLayout is a ValueError
        raise HTTPException(422, str(refusal)) from refusal


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
    frontmatter = {**parsed.frontmatter, **composed.statements(body)}
    return _geometry(lambda: geometry_response(
        composed.puml, artifact_id, frontmatter, _repo_root(), catalogs.ontology, generated=True,
        arrangement=body.arrangement, previous=frozenset(alias_by_instance(parsed.frontmatter)),
    ))


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
    return _written_layout("diagrams_patch_diagram_layout", artifact_id, body.patch, body.dry_run, catalogs)


class LayoutIntentsBody(BaseModel):
    """What the editor means, in order: ``align`` (``keys``, ``edge``), ``distribute`` (``keys``, ``axis``),
    ``straighten`` (``relations``) and ``return_to_automatic`` (``keys``; none for the whole layout).
    Each compiles to the layout patch that states it, checked against the stored layout."""

    model_config = ConfigDict(extra="forbid")

    intents: list[dict[str, Any]]
    dry_run: bool = True


@router.post(
    "/api/diagrams/{artifact_id}/layout/arrange", tags=[TAG_DIAGRAMS],
    summary="Align, distribute, straighten or return a diagram's layout to automatic",
    response_model=DiagramLayoutIntentsResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES,
)
def arrange_diagram_layout_gui(artifact_id: str, body: LayoutIntentsBody, catalogs: Catalogs) -> dict[str, object]:
    try:
        patch = intents_patch(body.intents, _stored_diagram(artifact_id), artifact_id, _repo_root(), catalogs.ontology)
    except ValueError as refusal:  # MalformedLayout is a ValueError
        raise HTTPException(400 if isinstance(refusal, MalformedLayout) else 422, str(refusal)) from refusal
    return _written_layout(
        "diagrams_arrange_diagram_layout", artifact_id, patch, body.dry_run, catalogs, with_patch=True,
    )


def _written_layout(
    operation: str, artifact_id: str, patch: Mapping[str, object] | PatchOf, dry_run: bool, catalogs: RuntimeCatalogs,
    *, with_patch: bool = False,
) -> dict[str, object]:
    """The layout write both routes make, through the write queue, with one mapping of its refusals.

    *with_patch* also answers the patch applied: the intents route's caller did not state it.
    """
    from src.infrastructure.write.artifact_write.diagram_layout_patch import patch_diagram_layout  # noqa: PLC0415

    repo_root, _, verifier = s.get_write_deps(catalogs)
    try:
        result = s.authorized_write(
            operation, patch_diagram_layout,
            repo_root=repo_root, verifier=verifier, clear_repo_caches=s.clear_caches,
            assert_write_root=assert_engagement_write_root, artifact_id=artifact_id, patch=patch,
            first_layout=lambda body_text, frontmatter: first_layout_of(
                body_text, frontmatter, repo_root, catalogs.ontology
            ),
            dry_run=dry_run,
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
        **({"patch": dict(result.patch)} if with_patch else {}),
    }
