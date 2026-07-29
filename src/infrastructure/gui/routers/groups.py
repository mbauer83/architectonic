"""Group lifecycle REST endpoints (T7.3.1)."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.application.assurance_diagrams import assurance_surface_diagram_types
from src.domain.repository.groups import GroupAxis, GroupEntry, GroupRegistry
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import TAG_GROUPS, WRITE_RESPONSES, OpenMapResponse

router = APIRouter()


class CreateGroupBody(BaseModel):
    kind: str
    slug: str
    name: str
    description: str = ""
    order: int = 0
    meta_ontology: str = ""
    type_filter: list[str] = []


class RenameGroupBody(BaseModel):
    kind: str
    target: str
    name: str | None = None
    new_slug: str | None = None


class ArchiveGroupBody(BaseModel):
    kind: str
    target: str
    confirm: str | None = None


class UnarchiveGroupBody(BaseModel):
    kind: str
    target: str


class UpdateGroupBody(BaseModel):
    kind: str
    target: str
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
        from src.infrastructure.gui.routers.entity_listing import engagement_model_catalog  # noqa: PLC0415

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
    response_model=OpenMapResponse)
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


async def _exec_op(route: tuple[str, str], **kwargs: Any) -> dict[str, Any]:
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.infrastructure.write.artifact_write.group_ops import GroupOpError, group_op  # noqa: PLC0415

    try:
        result = await s.authorized_write_async(route, group_op, repo_root, **kwargs)
    except GroupOpError as exc:
        raise HTTPException(400, str(exc))
    await asyncio.to_thread(s.refresh_now)
    from src.infrastructure.gui.routers.events import event_bus  # noqa: PLC0415

    await event_bus.publish({"type": "artifact_write_completed"})
    return dict(result)


@router.post("/api/group", tags=[TAG_GROUPS], summary="Create a group", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def create_group(body: CreateGroupBody) -> dict[str, Any]:
    return await _exec_op(
        ("POST", "/api/group"),
        axis=body.kind,
        action="create",
        target=body.slug,
        name=body.name,
        description=body.description,
        order=body.order,
        meta_ontology=body.meta_ontology,
        type_filter=body.type_filter or None,
    )


@router.put("/api/group", tags=[TAG_GROUPS], summary="Rename a group", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def rename_group(body: RenameGroupBody) -> dict[str, Any]:
    return await _exec_op(
        ("PUT", "/api/group"),
        axis=body.kind,
        action="rename",
        target=body.target,
        name=body.name,
        new_slug=body.new_slug,
    )


@router.post("/api/group/archive", tags=[TAG_GROUPS], summary="Archive a group", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def archive_group(body: ArchiveGroupBody) -> dict[str, Any]:
    return await _exec_op(
        ("POST", "/api/group/archive"), axis=body.kind, action="archive", target=body.target, confirm=body.confirm
    )


@router.post("/api/group/unarchive", tags=[TAG_GROUPS], summary="Unarchive a group", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def unarchive_group(body: UnarchiveGroupBody) -> dict[str, Any]:
    return await _exec_op(("POST", "/api/group/unarchive"), axis=body.kind, action="unarchive", target=body.target)


@router.patch("/api/group", tags=[TAG_GROUPS], summary="Update a group (partial)", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def update_group(body: UpdateGroupBody) -> dict[str, Any]:
    return await _exec_op(
        ("PATCH", "/api/group"),
        axis=body.kind,
        action="update",
        target=body.target,
        name=body.name,
        description=body.description,
        meta_ontology=body.meta_ontology or "",
        type_filter=body.type_filter,
    )


@router.delete("/api/group", tags=[TAG_GROUPS], summary="Delete a group", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
async def delete_group(
    kind: str = Query(...),
    target: str = Query(...),
    confirm: str | None = Query(default=None),
) -> dict[str, Any]:
    return await _exec_op(("DELETE", "/api/group"), axis=kind, action="delete", target=target, confirm=confirm)
