"""The picture a candidate is sketched on, served with the candidate as the subject (`candidates.picture`).

The counterparts of a diagram's editor reads — its context, its geometry, a session's drawing and resized
shapes — for a candidate, which needs no stored diagram: its picture starts from the stored diagram its stack
is drawn on where there is one, else from a view generated from what it reads over, or from nothing. The
editor is one component either way; only where it reads its picture from differs. Every route here writes
nothing.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.modeling.diagram_identities import strings_of
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.candidates.picture import (
    PictureStart,
    placed_instances,
    start_frontmatter,
    start_geometry,
    start_of,
    start_record,
)
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.drawing_wire import reshaped
from src.infrastructure.rest.contracts.candidate_picture import CandidatePictureContext
from src.infrastructure.rest.contracts.diagram_layout_editing import (
    DiagramLayoutGeometryResponse,
    ShapeDrawingsResponse,
)
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._candidate_access import refusals, service
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_CHANGES, WRITE_RESPONSES
from src.infrastructure.rest.routers.diagrams._geometry_proposals import GeometryPreviewBody
from src.infrastructure.rest.routers.diagrams._layout import DrawShapesBody, _geometry, _repo_root
from src.infrastructure.rest.routers.diagrams._picture_context import picture_context_payload
from src.infrastructure.rest.routers.diagrams._picture_preview import previewed_geometry
from src.infrastructure.rest.routers.diagrams.router import _read_diagram_impl

router = APIRouter()

Catalogs = Annotated[RuntimeCatalogs, Depends(runtime_catalogs_dependency)]

#: What the editor reads of the diagram a picture starts from, as a diagram read answers it.
_START_FIELDS = (
    "artifact_id", "name", "diagram_type", "entity_ids_used", "connection_ids_used", "diagram_entities",
    "authored_groupings", "extra",
)


def _start(artifact_id: str) -> PictureStart:
    with refusals():
        return start_of(service(), artifact_id)


@router.get(
    "/api/change-sets/{artifact_id}/picture/context",
    operation_id="changes_read_candidate_picture_context",
    tags=[TAG_CHANGES],
    summary="Read a candidate's picture with everything its editor needs",
    response_model=CandidatePictureContext,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def changes_read_candidate_picture_context(artifact_id: str, catalogs: Catalogs) -> dict[str, Any]:
    """What the picture starts from — a stored diagram's membership, or the generated view's — with the
    relations the model holds among, and the elements one and two steps from, what it draws and every element
    the candidate reads over."""
    start = _start(artifact_id)
    repo = s.get_repo()
    record, body = start_record(start, repo, _repo_root())
    if start.diagram is not None:
        read = _read_diagram_impl(start.diagram.artifact_id, catalogs)
        diagram = {key: read[key] for key in _START_FIELDS if read.get(key) is not None}
    else:
        diagram = {
            "artifact_id": "", "name": start.name, "diagram_type": start.generated.diagram_type,
            "entity_ids_used": strings_of(record.extra.get("entity-ids-used")),
            "connection_ids_used": strings_of(record.extra.get("connection-ids-used")),
        }
    return {"diagram": diagram, **picture_context_payload(
        repo, record, body, catalogs, read_entities=diagram.get("diagram_entities") or {}, reach=start.scope,
    )}


@router.get(
    "/api/change-sets/{artifact_id}/picture",
    operation_id="changes_read_candidate_picture",
    tags=[TAG_CHANGES],
    summary="Read the picture a candidate is sketched on",
    response_model=DiagramLayoutGeometryResponse,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def changes_read_candidate_picture(artifact_id: str, catalogs: Catalogs) -> dict[str, object]:
    """The stored diagram's picture, the view generated from what the candidate reads over, or the empty
    picture of a candidate that reads over nothing yet."""
    start = _start(artifact_id)
    return _geometry(lambda: start_geometry(start, s.get_repo(), _repo_root(), catalogs.ontology))


@router.post(
    "/api/change-sets/{artifact_id}/picture/preview",
    operation_id="changes_preview_candidate_picture",
    tags=[TAG_CHANGES],
    summary="Draw an edit session's composition over the picture a candidate is sketched on",
    response_model=DiagramLayoutGeometryResponse,
    response_model_exclude_none=True,
    # A write-shaped operation that mutates nothing, as the diagram preview is.
    responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def changes_preview_candidate_picture(
    artifact_id: str, body: GeometryPreviewBody, catalogs: Catalogs,
) -> dict[str, object]:
    """The session's composition, with the elements and relations it proposes, drawn over where the picture
    starts; a composition that draws nothing is the empty picture. Writes nothing."""
    start = _start(artifact_id)
    repo, root = s.get_repo(), _repo_root()
    base = start_frontmatter(start, repo, root)
    return _geometry(lambda: previewed_geometry(
        body, base, artifact_id=start.artifact_id, repo=repo, root=root, catalogs=catalogs,
        previous=placed_instances(base),
    ))


@router.post(
    "/api/change-sets/{artifact_id}/picture/shapes/preview",
    operation_id="changes_preview_candidate_picture_shapes",
    tags=[TAG_CHANGES],
    summary="Draw resized shapes of the picture a candidate is sketched on, writing nothing",
    response_model=ShapeDrawingsResponse,
    response_model_exclude_none=True,
    responses={**READ_RESPONSES, **WRITE_RESPONSES},
)
def changes_preview_candidate_picture_shapes(artifact_id: str, body: DrawShapesBody) -> dict[str, object]:
    """Each shape drawn by the composer at its new size; the candidate must be stored (404)."""
    _start(artifact_id)
    try:
        return {"drawings": [reshaped(shape.model_dump()) for shape in body.shapes]}
    except Unreadable as unreadable:
        raise HTTPException(422, f"This shape cannot be drawn: {unreadable.met}") from unreadable
