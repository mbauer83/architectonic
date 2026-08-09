"""Scratchpad REST endpoints.

Five operations over one resource, and the resource is the aggregate. There is no note route and no
link route: the root enforces the invariants, a partial update cannot be validated without loading
the whole thing anyway, and one shape removes the class of bug where two partial updates interleave
into a state neither writer intended.

The canvas is expected to batch and debounce **in the browser**, so this surface sees a save and
never a drag. That is a property of the client, asserted there — but the shape here is what makes it
possible: one idempotent replace carrying the version the writer read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.scratchpad.document import from_document, summary_to_document, to_response
from src.application.scratchpad.ports import ScratchpadNotFoundError, ScratchpadVersionConflictError
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import ScratchpadError
from src.infrastructure.rest.contracts.scratchpads import ScratchpadListResponse, ScratchpadResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_SCRATCHPADS,
    WRITE_RESPONSES,
)
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository

if TYPE_CHECKING:
    from src.domain.modules.module_registry import ModuleRegistry

router = APIRouter()


def _registry() -> "ModuleRegistry":
    """The module registry, so a served link can carry its verdict. One lookup per response."""
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _service() -> ScratchpadService:
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Engagement repository is not initialised")
    return ScratchpadService(YamlScratchpadRepository(repo_root))


class _ClosedBody(BaseModel):
    """Bodies are closed: a field the server does not know is a client believing something."""

    model_config = ConfigDict(extra="forbid")


class CreateScratchpadBody(_ClosedBody):
    """A create names the group, because a scratchpad has to live somewhere on disk — and only
    that. The four areas are seeded, so a caller who has decided nothing still gets a usable
    canvas."""

    name: str
    group: str
    description: str = ""
    meta_ontology: str = Field(default="archimate-4", alias="meta-ontology")
    seed_areas: bool = Field(default=True, alias="seed-areas")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ReplaceScratchpadBody(_ClosedBody):
    """The whole aggregate plus the version it was read at.

    `version` is required rather than optional: an optional concurrency token is one every client
    eventually omits, and the first time two people have the same scratchpad open, one of them
    silently loses an afternoon.
    """

    version: str
    group: str
    scratchpad: dict[str, Any]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _refuse(exc: Exception) -> HTTPException:
    """Map the domain's refusal vocabulary onto status codes, keeping the message verbatim.

    The messages name the offending id and say what to do, and they are read by agents as often as
    by people — rewording them here would leave the caller with a worse sentence than the one the
    aggregate wrote.
    """
    if isinstance(exc, ScratchpadNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, ScratchpadVersionConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/api/scratchpads", tags=[TAG_SCRATCHPADS], summary="List scratchpads",
    response_model=ScratchpadListResponse, response_model_exclude_none=True,
)
def list_scratchpads(
    group: str | None = Query(default=None, description="Restrict to one collection"),
    status_filter: str | None = Query(default=None, alias="status", description="Restrict to one status"),
) -> dict[str, Any]:
    summaries = _service().list_scratchpads(group=group, status=status_filter)
    return {"scratchpads": [summary_to_document(summary) for summary in summaries]}


@router.get(
    "/api/scratchpads/{artifact_id}", tags=[TAG_SCRATCHPADS], summary="Read a scratchpad whole",
    response_model=ScratchpadResponse, response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def read_scratchpad(artifact_id: str) -> dict[str, Any]:
    service = _service()
    try:
        scratchpad = service.read(artifact_id)
        return to_response(scratchpad, group=service.group_of(artifact_id), registry=_registry())
    except ScratchpadNotFoundError as exc:
        raise _refuse(exc) from exc


@router.post(
    "/api/scratchpads", tags=[TAG_SCRATCHPADS], summary="Create a scratchpad",
    response_model=ScratchpadResponse, response_model_exclude_none=True,
    responses=WRITE_RESPONSES, status_code=status.HTTP_201_CREATED,
)
def create_scratchpad(body: CreateScratchpadBody, response: Response) -> dict[str, Any]:
    from src.application.modeling.artifact_write import generate_entity_id  # noqa: PLC0415

    artifact_id = generate_entity_id("SCR", body.name)
    service = _service()
    try:
        created = s.authorized_write(
            "scratchpads_create_scratchpad",
            service.create,
            artifact_id=artifact_id,
            name=body.name,
            group=body.group,
            description=body.description,
            meta_ontology=body.meta_ontology,
            seed_areas=body.seed_areas,
        )
    except (ScratchpadError, ScratchpadVersionConflictError) as exc:
        raise _refuse(exc) from exc
    response.headers["Location"] = f"/api/scratchpads/{created.artifact_id}"
    return to_response(created, group=body.group, registry=_registry())


@router.put(
    "/api/scratchpads/{artifact_id}", tags=[TAG_SCRATCHPADS], summary="Replace a scratchpad whole",
    response_model=ScratchpadResponse, response_model_exclude_none=True,
    responses={**WRITE_RESPONSES, **READ_RESPONSES},
)
def replace_scratchpad(artifact_id: str, body: ReplaceScratchpadBody) -> dict[str, Any]:
    service = _service()
    try:
        incoming = from_document(body.scratchpad, artifact_id=artifact_id)
        stored = s.authorized_write(
            "scratchpads_replace_scratchpad",
            service.replace,
            incoming,
            group=body.group,
            expected_version=body.version,
        )
    except (ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError) as exc:
        raise _refuse(exc) from exc
    return to_response(stored, group=body.group, registry=_registry())


@router.delete(
    "/api/scratchpads/{artifact_id}", tags=[TAG_SCRATCHPADS], summary="Delete a scratchpad",
    response_model=None, responses={**WRITE_RESPONSES, **READ_RESPONSES},
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scratchpad(
    artifact_id: str, response: Response, dry_run: bool = True,
) -> dict[str, Any] | None:
    """Plans unless told otherwise, like every other write on this surface.

    Model content the scratchpad lifted or bound is never touched — what a scratchpad put into the
    model is not the scratchpad's to retract — so the plan reports what the deletion removes rather
    than a cascade it might trigger.
    """
    service = _service()
    try:
        scratchpad = service.read(artifact_id)
    except ScratchpadNotFoundError as exc:
        raise _refuse(exc) from exc
    if dry_run:
        # A committed removal has nothing to report; a plan has one, which needs a status that
        # permits a body.
        response.status_code = status.HTTP_200_OK
        return {
            "would_delete": scratchpad.artifact_id,
            "notes": len(scratchpad.notes),
            "links": len(scratchpad.links),
        }
    s.authorized_write("scratchpads_delete_scratchpad", service.delete, artifact_id)
    return None
