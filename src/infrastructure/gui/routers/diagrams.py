"""Diagram read and search endpoints."""

from __future__ import annotations

from functools import lru_cache as _lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.artifact_parsing import parse_diagram_source
from src.application.assurance_diagrams import assurance_surface_diagram_types
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog, runtime_catalogs_dependency
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._diagram_context import (
    candidate_connections_for_entities,
    diagram_context_payload,
    diagram_entities_and_puml,
    diagram_kind_connection_type_items,
    diagram_kind_entity_type_items,
    entity_display_item,
    hop_suggestions,
    puml_contains,
)
from src.infrastructure.gui.routers._diagram_edge_label import router as _edge_label_router
from src.infrastructure.gui.routers._diagram_serving import _rendered_path
from src.infrastructure.gui.routers._diagram_serving import router as _serving_router
from src.infrastructure.gui.routers._diagram_write import router as _write_router
from src.infrastructure.gui.routers._entity_display_search import entity_display_search_impl
from src.infrastructure.gui.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS, OpenMapResponse

router = APIRouter()
router.include_router(_write_router)
router.include_router(_edge_label_router)
router.include_router(_serving_router)


@_lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def _read_diagram_impl(id: str, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    result = s.get_repo().read_artifact(id, mode="full")
    if result is None or result.get("record_type") != "diagram":
        raise HTTPException(404, f"Diagram not found: {id!r}")
    diag_rec = s.get_repo().get_diagram(id)
    if diag_rec:
        raw_diagram_entities = diag_rec.extra.get("diagram-entities")
        diagram_entities = raw_diagram_entities if isinstance(raw_diagram_entities, dict) else {}
        local_connections = diag_rec.extra.get("connections")
        if local_connections:
            diagram_entities = {**diagram_entities, "_connections": local_connections}
        result["diagram_entities"] = diagram_entities or None
        _png = _rendered_path(diag_rec, ".png")
        result["rendered_filename"] = _png.name if _png is not None else None
        result["is_global"] = s.is_global(diag_rec.path)
        parsed = parse_diagram_source(str(result.get("puml_source", "")))
        frontmatter = parsed["frontmatter"]
        entity_ids_used = frontmatter.get("entity-ids-used")
        connection_ids_used = frontmatter.get("connection-ids-used")
        if isinstance(entity_ids_used, list):
            result["entity_ids_used"] = [str(x) for x in entity_ids_used]
        if isinstance(connection_ids_used, list):
            result["connection_ids_used"] = [str(x) for x in connection_ids_used]
        result["viewpoint"] = frontmatter.get("viewpoint")
        dt = catalogs.diagram_types.find_diagram_type(diag_rec.diagram_type)
        if dt:
            result.update(dt.read_diagram_extras(parsed))
    return result


@router.get("/api/diagrams", tags=[TAG_DIAGRAMS], summary="List diagrams", response_model=OpenMapResponse)
def list_diagrams(
    diagram_type: str | None = None,
    status: str | None = None,
    group: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    store_projected = assurance_surface_diagram_types(complete_diagram_type_catalog())
    if diagram_type in store_projected:
        return {"total": 0, "items": []}
    diagrams = s.get_repo().list_diagrams(diagram_type=diagram_type, status=status, group=group)
    diagrams = [d for d in diagrams if d.diagram_type not in store_projected]
    # Tier filtering happens BEFORE totals so `total` is the facet's count.
    if scope == "global":
        diagrams = [d for d in diagrams if s.is_global(d.path)]
    elif scope == "engagement":
        diagrams = [d for d in diagrams if not s.is_global(d.path)]
    return {"total": len(diagrams), "items": [s.diagram_to_summary(d) for d in diagrams]}


@router.get(
    "/api/diagram",
    tags=[TAG_DIAGRAMS],
    summary="Read a diagram by id",
    response_model=OpenMapResponse,
    responses=READ_RESPONSES,
)
def read_diagram(
    id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    return _read_diagram_impl(id, catalogs)


@router.get(
    "/api/matrix-config",
    tags=[TAG_DIAGRAMS],
    summary="Matrix diagram configuration",
    response_model=OpenMapResponse,
)
def get_matrix_config(id: str) -> dict[str, Any]:
    """Return entity-ids, conn-type-configs, combined flag, and body for a matrix diagram."""
    repo = s.get_repo()
    diag_rec = repo.get_diagram(id)
    if diag_rec is None or diag_rec.diagram_type != "matrix":
        raise HTTPException(404, f"Matrix diagram not found: {id!r}")
    try:
        puml_source = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(500, f"Failed to read matrix diagram: {id!r}")
    parsed = parse_diagram_source(puml_source)
    fm = parsed["frontmatter"]
    raw_eids = fm.get("entity-ids")
    entity_ids = [str(x) for x in raw_eids] if isinstance(raw_eids, list) else []
    raw_from = fm.get("from-entity-ids")
    from_entity_ids = [str(x) for x in raw_from] if isinstance(raw_from, list) else None
    raw_to = fm.get("to-entity-ids")
    to_entity_ids = [str(x) for x in raw_to] if isinstance(raw_to, list) else None
    raw_configs = fm.get("conn-type-configs")
    conn_type_configs = (
        [
            {"conn_type": str(c.get("conn_type", "")), "active": bool(c.get("active", True))}
            for c in raw_configs
            if isinstance(c, dict)
        ]
        if isinstance(raw_configs, list)
        else []
    )
    raw_kws = fm.get("keywords")
    keywords = [str(k) for k in raw_kws] if isinstance(raw_kws, list) else []
    return {
        "artifact_id": diag_rec.artifact_id,
        "name": diag_rec.name,
        "status": diag_rec.status,
        "version": diag_rec.version,
        "keywords": keywords,
        "entity_ids": entity_ids,
        "from_entity_ids": from_entity_ids,
        "to_entity_ids": to_entity_ids,
        "conn_type_configs": conn_type_configs,
        "combined": bool(fm.get("combined", False)),
        "matrix_body": str(parsed["puml_body"]).strip(),
    }


@router.get(
    "/api/diagram-refs",
    tags=[TAG_DIAGRAMS],
    summary="Diagram references for a source/target pair",
    response_model=list[OpenMapResponse],
)
def get_diagram_refs(source_id: str, target_id: str) -> list[dict[str, str]]:
    repo = s.get_repo()
    src = repo.get_entity(source_id)
    tgt = repo.get_entity(target_id)
    if not src or not tgt or not src.display_alias or not tgt.display_alias:
        return []
    return [
        {"artifact_id": d.artifact_id, "name": d.name}
        for d in repo.list_diagrams()
        if puml_contains(d, src.display_alias, tgt.display_alias)
    ]


@router.get(
    "/api/diagram-entities",
    tags=[TAG_DIAGRAMS],
    summary="Entities placed on a diagram",
    response_model=list[OpenMapResponse],
)
def get_diagram_entities(
    id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> list[dict[str, Any]]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {id!r}")
    entities, _puml = diagram_entities_and_puml(repo, diag_rec, catalogs)
    return entities


@router.get(
    "/api/diagram-connections",
    tags=[TAG_DIAGRAMS],
    summary="Connections drawn on a diagram",
    response_model=list[OpenMapResponse],
)
def get_diagram_connections(
    id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> list[dict[str, Any]]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {id!r}")
    return diagram_context_payload(repo, diag_rec, catalogs)["connections"]


@router.get(
    "/api/diagram-context",
    tags=[TAG_DIAGRAMS],
    summary="Diagram with its resolved context",
    response_model=OpenMapResponse,
    responses=READ_RESPONSES,
)
def get_diagram_context(
    id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {id!r}")
    return diagram_context_payload(repo, diag_rec, catalogs)


@router.get(
    "/api/diagram-types/{name}/entity-types",
    tags=[TAG_DIAGRAMS],
    summary="Entity types a diagram type accepts",
    response_model=list[OpenMapResponse],
    responses=READ_RESPONSES,
)
def get_diagram_kind_entity_types(
    name: str,
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> list[dict[str, Any]]:
    try:
        return diagram_kind_entity_type_items(name, catalogs, viewpoint=viewpoint)
    except KeyError:
        raise HTTPException(404, f"Diagram type not found: {name!r}")


@router.get(
    "/api/diagram-types/{name}/connection-types",
    tags=[TAG_DIAGRAMS],
    summary="Connection types a diagram type accepts",
    response_model=list[OpenMapResponse],
    responses=READ_RESPONSES,
)
def get_diagram_kind_connection_types(
    name: str,
    viewpoint: str | None = None,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> list[dict[str, Any]]:
    try:
        return diagram_kind_connection_type_items(name, catalogs, viewpoint=viewpoint)
    except KeyError:
        raise HTTPException(404, f"Diagram type not found: {name!r}")


@router.get(
    "/api/entity-display-item",
    tags=[TAG_DIAGRAMS],
    summary="Display item for one entity",
    response_model=OpenMapResponse,
    responses=READ_RESPONSES,
)
def get_entity_display_item(
    id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    rec = repo.get_entity(id)
    if rec is None:
        raise HTTPException(404, f"Entity {id!r} not found")
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
