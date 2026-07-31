"""What a diagram kind accepts, and what can be placed on one: the palette reads.

Split from the diagram reads when that module passed the size limit. The seam is real: nothing here
addresses a diagram. These answer questions about a diagram *type* — which entity and connection
types it admits, optionally narrowed by a viewpoint — and about the entities a user could add to one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.contracts.diagrams import (
    DiagramTypeConnectionTypeListResponse,
    DiagramTypeEntityTypeListResponse,
)
from src.infrastructure.gui.contracts.entities import EntityDisplayItemResponse
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._diagram_context import (
    candidate_connections_for_entities,
    diagram_kind_connection_type_items,
    diagram_kind_entity_type_items,
    entity_display_item,
    hop_suggestions,
)
from src.infrastructure.gui.routers._entity_display_search import entity_display_search_impl
from src.infrastructure.gui.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS, OpenMapResponse

router = APIRouter()


@router.get(
    "/api/diagram-types/{diagram_type}/entity-types",
    tags=[TAG_DIAGRAMS],
    summary="Entity types a diagram type accepts",
    response_model=DiagramTypeEntityTypeListResponse,
    responses=READ_RESPONSES,
)
def get_diagram_kind_entity_types(
    diagram_type: str,
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    try:
        return {"items": diagram_kind_entity_type_items(diagram_type, catalogs, viewpoint=viewpoint)}
    except KeyError:
        raise HTTPException(404, f"Diagram type not found: {diagram_type!r}")


@router.get(
    "/api/diagram-types/{diagram_type}/connection-types",
    tags=[TAG_DIAGRAMS],
    summary="Connection types a diagram type accepts",
    response_model=DiagramTypeConnectionTypeListResponse,
    responses=READ_RESPONSES,
)
def get_diagram_kind_connection_types(
    diagram_type: str,
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    try:
        return {
            "items": diagram_kind_connection_type_items(diagram_type, catalogs, viewpoint=viewpoint)
        }
    except KeyError:
        raise HTTPException(404, f"Diagram type not found: {diagram_type!r}")


@router.get(
    "/api/entities/{artifact_id}/display-item",
    tags=[TAG_DIAGRAMS],
    summary="Display item for one entity",
    response_model=EntityDisplayItemResponse,
    responses=READ_RESPONSES,
)
def get_entity_display_item(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    rec = repo.get_entity(artifact_id)
    if rec is None:
        raise HTTPException(404, f"Entity {artifact_id!r} not found")
    return entity_display_item(rec, catalogs)


@router.get(
    "/api/entity-display-search",
    tags=[TAG_DIAGRAMS],
    summary="Search entities for diagram placement",
    response_model=OpenMapResponse,
)
def entity_display_search(
    q: str,
    limit: int = Query(default=20, le=50),
    diagram_type: str | None = None,
    domains: str | None = None,
    entity_types: str | None = None,
    keywords: str | None = None,
    cursor: str | None = None,
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    result = entity_display_search_impl(
        q, limit, diagram_type, catalogs,
        domains=domains, entity_types=entity_types, keywords=keywords, cursor=cursor, viewpoint=viewpoint,
    )
    return {"items": result.items, "next_cursor": result.next_cursor}


@router.get(
    "/api/diagram-entity-discovery",
    tags=[TAG_DIAGRAMS],
    summary="Discover entities to add to a diagram",
    response_model=OpenMapResponse,
)
def diagram_entity_discovery(
    q: str | None = None,
    included_entity_ids: str | None = None,
    diagram_type: str | None = None,
    max_hops: int = Query(default=2, ge=1, le=4),
    limit: int = Query(default=20, ge=1, le=50),
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    included = [
        entity_id.strip()
        for entity_id in (included_entity_ids or "").split(",")
        if entity_id.strip() and repo.get_entity(entity_id.strip()) is not None
    ]
    excluded = set(included)
    search_results: list[dict[str, Any]] = (
        entity_display_search_impl(q or "", limit, diagram_type, catalogs, viewpoint=viewpoint).items
        if (q or "").strip() else []
    )
    search_results = [item for item in search_results if str(item["artifact_id"]) not in excluded][:limit]
    return {
        "search_results": search_results,
        "candidate_connections": candidate_connections_for_entities(repo, included),
        "suggested_entities": hop_suggestions(repo, included, catalogs, max_hops=max_hops, limit_per_hop=limit),
    }
