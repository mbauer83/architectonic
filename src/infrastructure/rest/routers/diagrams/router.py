"""Diagram read and search endpoints."""

from __future__ import annotations

from functools import lru_cache as _lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.artifacts.parsing import parse_diagram_source
from src.application.assurance.diagrams import assurance_surface_diagram_types
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog, runtime_catalogs_dependency
from src.infrastructure.rest.contracts.diagrams import (
    DiagramConnectionListResponse,
    DiagramContextResponse,
    DiagramDetailResponse,
    DiagramEntityListResponse,
    DiagramListResponse,
    DiagramReferenceListResponse,
    MatrixConfigResponse,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS
from src.infrastructure.rest.routers.diagrams._context import (
    diagram_context_payload,
    diagram_entities_and_puml,
    puml_contains,
)
from src.infrastructure.rest.routers.diagrams._edge_label import router as _edge_label_router
from src.infrastructure.rest.routers.diagrams._matrix_write import router as _matrix_write_router
from src.infrastructure.rest.routers.diagrams._palette import router as _palette_router
from src.infrastructure.rest.routers.diagrams._serving import _rendered_path
from src.infrastructure.rest.routers.diagrams._serving import router as _serving_router
from src.infrastructure.rest.routers.diagrams._sub_entity import router as _sub_entity_router
from src.infrastructure.rest.routers.diagrams._write import router as _write_router

router = APIRouter()
router.include_router(_write_router)
router.include_router(_matrix_write_router)
router.include_router(_palette_router)
router.include_router(_edge_label_router)
router.include_router(_serving_router)
router.include_router(_sub_entity_router)


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
            # Two hooks, because the module is doing two things. A replacement for a field the
            # envelope declares goes into that field; the module's own keys go under `type_extras`,
            # which is the one level of this response whose properties are the module's to decide.
            resolved = dt.resolve_diagram_entities(parsed, diagram_entities)
            if resolved is not None:
                result["diagram_entities"] = resolved
            result["type_extras"] = dt.read_diagram_extras(parsed) or None
    return result


@router.get("/api/diagrams", tags=[TAG_DIAGRAMS], summary="List diagrams",
    response_model=DiagramListResponse)
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
    "/api/diagrams/{artifact_id}",
    tags=[TAG_DIAGRAMS],
    summary="Read a diagram by id",
    response_model=DiagramDetailResponse,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def read_diagram(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    return _read_diagram_impl(artifact_id, catalogs)


@router.get(
    "/api/matrices/{artifact_id}/config",
    tags=[TAG_DIAGRAMS],
    summary="Matrix diagram configuration",
    response_model=MatrixConfigResponse,
    responses=READ_RESPONSES,
)
def get_matrix_config(artifact_id: str) -> dict[str, Any]:
    """Return entity-ids, conn-type-configs, combined flag, and body for a matrix diagram.

    Addressed under ``/api/matrices`` because a matrix is a diagram of the matrix kind and this is
    the kind-specific projection of it — asking for the config of a non-matrix diagram is a 404, not
    an empty answer."""
    id = artifact_id
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
    response_model=DiagramReferenceListResponse,
)
def get_diagram_refs(source_id: str, target_id: str) -> dict[str, Any]:
    repo = s.get_repo()
    src = repo.get_entity(source_id)
    tgt = repo.get_entity(target_id)
    if not src or not tgt or not src.display_alias or not tgt.display_alias:
        return {"items": []}
    return {
        "items": [
            {"artifact_id": d.artifact_id, "name": d.name}
            for d in repo.list_diagrams()
            if puml_contains(d, src.display_alias, tgt.display_alias)
        ]
    }


@router.get(
    "/api/diagrams/{artifact_id}/entities",
    tags=[TAG_DIAGRAMS],
    summary="Entities placed on a diagram",
    response_model=DiagramEntityListResponse,
    responses=READ_RESPONSES,
)
def get_diagram_entities(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    entities, _puml = diagram_entities_and_puml(repo, diag_rec, catalogs)
    return {"items": entities}


@router.get(
    "/api/diagrams/{artifact_id}/connections",
    tags=[TAG_DIAGRAMS],
    summary="Connections drawn on a diagram",
    response_model=DiagramConnectionListResponse,
    responses=READ_RESPONSES,
)
def get_diagram_connections(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    return {"items": diagram_context_payload(repo, diag_rec, catalogs)["connections"]}


@router.get(
    "/api/diagrams/{artifact_id}/context",
    tags=[TAG_DIAGRAMS],
    summary="Diagram with its resolved context",
    response_model=DiagramContextResponse,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def get_diagram_context(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    return diagram_context_payload(repo, diag_rec, catalogs)
