"""Arranging a diagram: the picture an editor arranges, shapes drawn at a new size, and a layout patch.

The picture is drawn under the reader's lens where one is given, so an editor arranges what the reader
was reading: the printed attributes, the colouring, the legend (owner, 2026-11-25). The read and the
drawing write nothing. The patch is the one write: entries of the layout block,
applied to the stored layout — or, on a diagram PlantUML still arranges, to the first layout taken
over from its picture — and written through the diagram edit, so it is refused and verified as any
layout is.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.application.modeling.diagram_identities import alias_by_instance
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import MalformedLayout
from src.domain.diagrams.layout.layout_patch import LayoutConflict
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch, stated_intents
from src.infrastructure.rendering.laid_out_rendering import stored_layout
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.diagram_geometry import (
    geometry_response,
    stored_geometry,
)
from src.infrastructure.rendering.layout.diagram_picture import (
    NotDrawn,
    RendererUnavailable,
    first_layout_of,
)
from src.infrastructure.rendering.layout.drawing_wire import reshaped
from src.infrastructure.rendering.layout.surround_placement import carried_by, occupied
from src.infrastructure.rest.contracts.diagram_layout_editing import (
    DiagramLayoutGeometryResponse,
    DiagramLayoutIntentsResponse,
    DiagramLayoutPatchResponse,
    ShapeDrawingsResponse,
    SurroundPlacementResponse,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_DIAGRAMS,
    WRITE_RESPONSES,
)
from src.infrastructure.rest.routers.diagrams._geometry_proposals import GeometryPreviewBody
from src.infrastructure.rest.routers.diagrams._lensed_reading import kind_muting, lensed_body, reading_body
from src.infrastructure.rest.routers.diagrams._picture_preview import previewed_geometry
from src.infrastructure.rest.routers.diagrams._reading_lens_request import reading_lens
from src.infrastructure.rest.routers.diagrams._serving import _rendered_path
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.parse_existing import ParsedDiagram, parse_diagram_file

if TYPE_CHECKING:
    from src.infrastructure.write.artifact_write.diagram_layout_patch import LayoutPatchResult

router = APIRouter()

Catalogs = Annotated[RuntimeCatalogs, Depends(runtime_catalogs_dependency)]
Lens = Annotated[ReadingLens, Depends(reading_lens)]


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


class SurroundPlacementBody(BaseModel):
    """Where a diagram being arranged is now, and what was drawn round it: the parts' extents as drawn, and what
    the diagram occupied then (both as the geometry read handed them over); its shapes, the courses of its lines
    and its lines' labels as they are now."""

    model_config = ConfigDict(extra="forbid")

    drawn: ExtentBody
    parts: list[ExtentBody]
    shapes: list[ExtentBody]
    courses: list[list[tuple[float, float]]]
    labels: list[ExtentBody]


class PatchLayoutBody(BaseModel):
    """Entries of the layout block to change, by section and key (`diagram_layout_wire.LayoutPatch`)."""

    model_config = ConfigDict(extra="forbid")

    patch: LayoutPatch
    dry_run: bool = Field(True, description="Answer the layout that would be written, and write nothing.")


def _stored_record(artifact_id: str) -> DiagramRecord:
    record = s.get_repo().get_diagram(artifact_id)
    if record is None or not Path(record.path).exists():
        raise HTTPException(404, f"Diagram '{artifact_id}' not found")
    return record


def _stored_diagram(artifact_id: str) -> ParsedDiagram:
    return parse_diagram_file(Path(_stored_record(artifact_id).path))


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
def read_diagram_layout_geometry(artifact_id: str, catalogs: Catalogs, lens: Lens) -> dict[str, object]:
    parsed = _stored_diagram(artifact_id)
    if lens.is_empty:
        return _geometry(lambda: stored_geometry(parsed, artifact_id, _repo_root(), catalogs.ontology))
    record = _stored_record(artifact_id)
    root = _repo_root()
    path = Path(record.path)
    # As the reader's picture is drawn (`_serving.get_diagram_svg`): printed lines held to the stored widths.
    body = reading_body(
        artifact_id, path, lens, catalogs, root, diagram_type=record.diagram_type,
        laid_out=stored_layout(path, catalogs.ontology), stored_svg=_rendered_path(record, ".svg"),
    )
    return _geometry(lambda: geometry_response(
        body, artifact_id, dict(parsed.frontmatter), root, catalogs.ontology,
        restyle_prepared=kind_muting(lens, root),
    ))


@contextmanager
def _renderer_available() -> Iterator[None]:
    """A server that cannot run PlantUML answers 503: the request was not at fault, and may be retried."""
    try:
        yield
    except RendererUnavailable as unavailable:
        raise HTTPException(503, str(unavailable)) from unavailable


def _geometry(read: Callable[[], dict[str, object]]) -> dict[str, object]:
    """A geometry read, refused as 422 where the picture cannot be drawn or the layout cannot be read."""
    try:
        with _renderer_available():
            return read()
    except ValueError as refusal:  # MalformedLayout is a ValueError
        raise HTTPException(422, str(refusal)) from refusal


@router.post(
    "/api/diagrams/{artifact_id}/layout/geometry/preview", tags=[TAG_DIAGRAMS],
    summary="Draw an unsaved diagram composition with layout keys", response_model=DiagramLayoutGeometryResponse,
    response_model_exclude_none=True, responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def preview_diagram_layout_geometry(
    artifact_id: str, body: GeometryPreviewBody, catalogs: Catalogs, lens: Lens,
) -> dict[str, object]:
    parsed = _stored_diagram(artifact_id)
    root = _repo_root()

    def lensed(authored: str) -> str:
        return lensed_body(artifact_id, Path(_stored_record(artifact_id).path), lens, catalogs, root, authored=authored)

    return _geometry(lambda: previewed_geometry(
        body, parsed.frontmatter, artifact_id=artifact_id, repo=s.get_repo(), root=root, catalogs=catalogs,
        previous=frozenset(alias_by_instance(parsed.frontmatter)),
        lensed=None if lens.is_empty else lensed, restyle=kind_muting(lens, root),
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
    """Each shape drawn by the composer at its new size. The drawing, where it was drawn and where it goes
    all arrive in the request; the address names the diagram they were read from, which must be stored (404)."""
    _stored_record(artifact_id)
    try:
        return {"drawings": [reshaped(shape.model_dump()) for shape in body.shapes]}
    except Unreadable as unreadable:
        raise HTTPException(422, f"This shape cannot be drawn: {unreadable.met}") from unreadable


@router.post(
    "/api/diagrams/{artifact_id}/layout/surround/preview", tags=[TAG_DIAGRAMS],
    summary="Place the title and legend of a diagram being arranged, writing nothing",
    response_model=SurroundPlacementResponse, response_model_exclude_none=True,
    responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def preview_diagram_surround(artifact_id: str, body: SurroundPlacementBody) -> dict[str, object]:
    """How far each part drawn round the diagram moves, by the composer's own rule (`surround_placement`), so
    the editor's canvas shows the title and the legend where the saved picture will. Needs nothing of the
    diagram but its address, which must be stored (404): where everything is arrives in the request, as the
    editor holds it."""
    _stored_record(artifact_id)
    was = _extent(body.drawn)
    now = occupied(
        map(_extent, body.shapes), ([Point(x, y) for x, y in course] for course in body.courses),
        map(_extent, body.labels),
    ) or was
    return {"moves": [carried_by(_extent(part), was, now) for part in body.parts]}


def _extent(body: ExtentBody) -> Extent:
    return Extent(body.left, body.top, body.right, body.bottom)


@router.patch(
    "/api/diagrams/{artifact_id}/layout", tags=[TAG_DIAGRAMS],
    summary="Change entries of a diagram's layout", response_model=DiagramLayoutPatchResponse,
    response_model_exclude_none=True,
    responses=WRITE_RESPONSES,
)
def patch_diagram_layout_gui(artifact_id: str, body: PatchLayoutBody, catalogs: Catalogs) -> dict[str, object]:
    from src.infrastructure.write.artifact_write.diagram_layout_patch import patch_diagram_layout  # noqa: PLC0415

    return _written_layout(
        "diagrams_patch_diagram_layout", patch_diagram_layout, catalogs,
        artifact_id=artifact_id, patch=body.patch.stated(), dry_run=body.dry_run,
    )


class LayoutIntentsBody(BaseModel):
    """What the editor means, in order (`diagram_layout_wire.ArrangeIntent`). Layout intents compile to the
    patch that states them, checked against the stored layout; grouping intents to the diagram's new
    groupings and the layout change that keeps the layout matching them, written in the same edit."""

    model_config = ConfigDict(extra="forbid")

    intents: list[ArrangeIntent] = Field(min_length=1)
    dry_run: bool = Field(True, description="Answer the patch and groupings that would be written, and write nothing.")


@router.post(
    "/api/diagrams/{artifact_id}/layout/arrange", tags=[TAG_DIAGRAMS],
    summary="Align, distribute, straighten, regroup or return a diagram's layout to automatic",
    response_model=DiagramLayoutIntentsResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES,
)
def arrange_diagram_layout_gui(artifact_id: str, body: LayoutIntentsBody, catalogs: Catalogs) -> dict[str, object]:
    from src.infrastructure.write.artifact_write.diagram_arrangement import arrange_diagram  # noqa: PLC0415

    _stored_record(artifact_id)
    return _written_layout(
        "diagrams_arrange_diagram_layout", arrange_diagram, catalogs, with_patch=True,
        artifact_id=artifact_id, stated=stated_intents(body.intents), ontology=catalogs.ontology,
        store=s.get_repo(), dry_run=body.dry_run,
    )


def _written_layout(
    operation: str, write: Callable[..., LayoutPatchResult], catalogs: RuntimeCatalogs, *,
    with_patch: bool = False, **arguments: Any,
) -> dict[str, object]:
    """The layout write both routes make, through the write queue, with one mapping of its refusals.

    *with_patch* also answers the patch applied: the intents route's caller did not state it. The groupings
    are answered where the write changed them.
    """
    repo_root, _, verifier = s.get_write_deps(catalogs)
    try:
        with _renderer_available():
            result = s.authorized_write(
                operation, write,
                repo_root=repo_root, verifier=verifier, clear_repo_caches=s.clear_caches,
                assert_write_root=assert_engagement_write_root,
                first_layout=lambda body_text, frontmatter: first_layout_of(
                    body_text, frontmatter, repo_root, catalogs.ontology
                ),
                **arguments,
            )
    except LayoutConflict as conflict:
        raise HTTPException(409, str(conflict)) from conflict
    except NotDrawn as refusal:
        raise HTTPException(422, str(refusal)) from refusal
    except (MalformedLayout, ValueError) as refusal:
        raise HTTPException(400, str(refusal)) from refusal
    return result.as_answer(with_patch=with_patch)
