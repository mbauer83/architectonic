"""Group lifecycle REST endpoints (T7.3.1)."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from src.application.assurance_diagrams import assurance_surface_diagram_types
from src.domain.repository.groups import GroupAxis, GroupEntry, GroupRegistry
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog
from src.infrastructure.rest.contracts.authoring_catalogs import GroupListResponse
from src.infrastructure.rest.contracts.groups import GroupOperationResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import TAG_GROUPS, WRITE_RESPONSES

router = APIRouter()


class _ClosedBody(BaseModel):
    """Request bodies are closed, so a caller still sending the retired identity fields is told.

    A group is named by the pair ``(kind, slug)``, and after the migration both live in the path.
    Silently ignoring a ``kind`` in the body would let a client believe it had addressed one axis
    while the URL addressed another.
    """

    model_config = ConfigDict(extra="forbid")


class CreateGroupBody(_ClosedBody):
    """A create carries the slug: it is the caller's chosen natural key, not a minted id, and the
    collection route has nowhere else to put it."""

    kind: str
    slug: str
    name: str
    description: str = ""
    order: int = 0
    meta_ontology: str = ""
    type_filter: list[str] = []


class RenameGroupBody(_ClosedBody):
    name: str | None = None
    new_slug: str | None = None


class ArchiveGroupBody(_ClosedBody):
    confirm: str | None = None


class UpdateGroupBody(_ClosedBody):
    name: str | None = None
    description: str | None = None
    meta_ontology: str | None = None
    type_filter: list[str] | None = None


def _entry_dict(e: GroupEntry, member_count: int) -> dict[str, Any]:
    return {
        "slug": e.slug,
        "id": e.id,
        "name": e.name,
        "description": e.description,
        "order": e.order,
        "archived": e.archived,
        "default": e.default,
        "meta_ontology": e.meta_ontology,
        "type_filter": list(e.type_filter),
        "member_count": member_count,
    }


def _axis_member_counts(kind: GroupAxis, store_projected: frozenset[str]) -> Counter[str]:
    """Whole-repo member counts per group slug, matching each axis's browse-list population —
    the sidebar badges must reflect the full catalog, never the currently loaded (group-filtered)
    page, or every non-active group reads zero.

    `store_projected` names the diagram types with no repository file to count, so the badge agrees
    with the list the user then sees."""
    repo = s.get_repo()
    if kind == "model-project":
        from src.infrastructure.rest.routers.entity_listing import engagement_model_catalog  # noqa: PLC0415

        return Counter(e.group for e in engagement_model_catalog(repo.list_entities()))
    if kind == "diagram-collection":
        return Counter(
            d.group for d in repo.list_diagrams()
            if d.diagram_type not in store_projected
        )
    if kind == "document-collection":
        return Counter(d.group for d in repo.list_documents())
    # analysis-collection members live in the (possibly locked) assurance store, not this repo.
    return Counter()


def _axis_entries(
    registry: GroupRegistry, kind: GroupAxis, store_projected: frozenset[str],
) -> list[dict[str, Any]]:
    counts = _axis_member_counts(kind, store_projected)
    return [_entry_dict(e, counts.get(e.slug, 0)) for e in registry.list_axis(kind)]


@router.get("/api/groups", tags=[TAG_GROUPS], summary="List model-project groups with member counts",
    # `exclude_none`: an axis the `kind` filter left out is absent, not an empty list — "not asked for"
    # and "has no groups" are different answers and a client branches on them differently.
    response_model=GroupListResponse, response_model_exclude_none=True)
def list_groups(kind: str | None = None) -> dict[str, Any]:
    """Return groups from the registry, optionally filtered by axis."""
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.application.group_registry import load_group_registry  # noqa: PLC0415

    registry = load_group_registry(repo_root)
    store_projected = assurance_surface_diagram_types(complete_diagram_type_catalog())
    result: dict[str, Any] = {}
    if kind is None or kind == "model-project":
        result["model-projects"] = _axis_entries(registry, "model-project", store_projected)
    if kind is None or kind == "diagram-collection":
        result["diagram-collections"] = _axis_entries(registry, "diagram-collection", store_projected)
    if kind is None or kind == "document-collection":
        result["document-collections"] = _axis_entries(registry, "document-collection", store_projected)
    if kind is None or kind == "analysis-collection":
        result["analysis-collections"] = _axis_entries(registry, "analysis-collection", store_projected)
    return result


async def _exec_op(operation_id: str, **kwargs: Any) -> dict[str, Any]:
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.infrastructure.write.artifact_write.group_ops import GroupOpError, group_op  # noqa: PLC0415

    try:
        result = await s.authorized_write_async(operation_id, group_op, repo_root, **kwargs)
    except GroupOpError as exc:
        raise HTTPException(400, str(exc))
    await asyncio.to_thread(s.refresh_now)
    from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415

    await event_bus.publish({"type": "artifact_write_completed"})
    return dict(result)


#: A create answers 201 and names the group in ``Location``.
_CREATE_RESPONSES: dict[int | str, Any] = dict(WRITE_RESPONSES)


@router.post("/api/groups", tags=[TAG_GROUPS], summary="Create a group", response_model=GroupOperationResponse,
    response_model_exclude_none=True,
    responses=_CREATE_RESPONSES, status_code=status.HTTP_201_CREATED)
async def create_group(body: CreateGroupBody, response: Response) -> dict[str, Any]:
    result = await _exec_op(
        "groups_create_group",
        axis=body.kind,
        action="create",
        target=body.slug,
        name=body.name,
        description=body.description,
        order=body.order,
        meta_ontology=body.meta_ontology,
        type_filter=body.type_filter or None,
    )
    response.headers["Location"] = _group_location(body.kind, body.slug)
    return result


def _group_location(kind: str, slug: str) -> str:
    return f"/api/groups/{quote(kind, safe='')}/{quote(slug, safe='')}"


@router.post("/api/groups/{kind}/{slug}/rename", tags=[TAG_GROUPS], summary="Rename a group",
    response_model=GroupOperationResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES)
async def rename_group(kind: str, slug: str, body: RenameGroupBody) -> dict[str, Any]:
    """An explicit action segment, not a ``PATCH`` field: renaming re-files every member, so it is
    a move rather than an attribute update, and it changes the resource's own address."""
    return await _exec_op(
        "groups_rename_group",
        axis=kind,
        action="rename",
        target=slug,
        name=body.name,
        new_slug=body.new_slug,
    )


@router.post("/api/groups/{kind}/{slug}/archive", tags=[TAG_GROUPS], summary="Archive a group",
    response_model=GroupOperationResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES)
async def archive_group(kind: str, slug: str, body: ArchiveGroupBody | None = None) -> dict[str, Any]:
    return await _exec_op(
        "groups_archive_group", axis=kind, action="archive", target=slug,
        confirm=body.confirm if body is not None else None,
    )


@router.post("/api/groups/{kind}/{slug}/unarchive", tags=[TAG_GROUPS], summary="Unarchive a group",
    response_model=GroupOperationResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES)
async def unarchive_group(kind: str, slug: str) -> dict[str, Any]:
    """No body: the path names the group and the segment names the action, so there is nothing left
    for a caller to say."""
    return await _exec_op("groups_unarchive_group", axis=kind, action="unarchive", target=slug)


@router.patch("/api/groups/{kind}/{slug}", tags=[TAG_GROUPS], summary="Update a group (partial)",
    response_model=GroupOperationResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES)
async def update_group(kind: str, slug: str, body: UpdateGroupBody) -> dict[str, Any]:
    return await _exec_op(
        "groups_update_group",
        axis=kind,
        action="update",
        target=slug,
        name=body.name,
        description=body.description,
        meta_ontology=body.meta_ontology or "",
        type_filter=body.type_filter,
    )


@router.delete("/api/groups/{kind}/{slug}", tags=[TAG_GROUPS], summary="Delete a group",
    response_model=GroupOperationResponse, response_model_exclude_none=True, responses=WRITE_RESPONSES)
async def delete_group(
    kind: str,
    slug: str,
    confirm: str | None = Query(default=None),
) -> dict[str, Any]:
    return await _exec_op("groups_delete_group", axis=kind, action="delete", target=slug, confirm=confirm)
