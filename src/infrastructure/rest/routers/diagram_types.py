"""Diagram-kind discovery endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application.assurance.diagrams import assurance_surface_diagram_types
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import complete_diagram_type_catalog, runtime_catalogs_dependency
from src.infrastructure.rest.contracts.diagram_types import (
    DiagramTypeListResponse,
    DiagramTypeUiConfigResponse,
)
from src.infrastructure.rest.contracts.diagrams import (
    DatatypeTypeListResponse,
    DatatypeTypeUsageResponse,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._diagram_type_payload import ui_config_payload
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS

router = APIRouter()


@router.get("/api/diagram-types", tags=[TAG_DIAGRAMS], summary="List diagram types",
    response_model=DiagramTypeListResponse)
def list_diagram_types(catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)) -> list[dict[str, str]]:
    store_projected = assurance_surface_diagram_types(complete_diagram_type_catalog())
    return [
        {
            "key": key,
            "label": kind.ui_config.label,
            "description": kind.ui_config.description,
        }
        for key, kind in sorted(catalogs.diagram_types.all_diagram_types().items())
        if key not in store_projected
    ]


@router.get("/api/diagram-types/{diagram_type}/ui-config", tags=[TAG_DIAGRAMS],
    summary="UI config for one diagram type", response_model=DiagramTypeUiConfigResponse,
    responses=READ_RESPONSES)
def read_diagram_kind_ui_config(
    diagram_type: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    kind = catalogs.diagram_types.find_diagram_type(diagram_type)
    if kind is None:
        raise HTTPException(404, f"Diagram type not found: {diagram_type!r}")
    return ui_config_payload(kind.ui_config)


@router.get("/api/diagram-types/datatype/types", tags=[TAG_DIAGRAMS], summary="Datatype classifier types",
    response_model=DatatypeTypeListResponse)
def query_datatype_type_catalog(
    query: str | None = None,
    scope: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    diagram_id: str | None = None,
) -> dict[str, Any]:
    from src.diagram_types.datatype import _config as _dt_config  # noqa: PLC0415
    from src.diagram_types.datatype._type_catalog import query_datatype_types  # noqa: PLC0415

    primitive_names = list(str(p) for p in (_dt_config.get("ui") or {}).get("primitive_types") or [])
    repo = s.get_repo()
    result = query_datatype_types(
        repo, primitive_names,
        query=query, scope=scope, kind=kind, limit=limit, cursor=cursor, diagram_id=diagram_id,
    )
    return {
        "generation": result.generation,
        "primitives": result.primitives,
        "classifiers": [
            {
                "type_id": c.type_id,
                "label": c.label,
                "kind": c.kind,
                "scope": c.scope,
                "host_diagram_id": c.host_diagram_id,
            }
            for c in result.classifiers
        ],
        "next_cursor": result.next_cursor,
    }


@router.get("/api/diagram-types/datatype/types/{type_id}/usages", tags=[TAG_DIAGRAMS],
    summary="Usages of a datatype classifier type", response_model=DatatypeTypeUsageResponse)
def query_datatype_type_usages(type_id: str) -> dict[str, Any]:
    from src.diagram_types.datatype._type_catalog import query_type_usages  # noqa: PLC0415

    repo = s.get_repo()
    usages = query_type_usages(repo, type_id=type_id)
    return {"type_id": type_id, "usages": usages}
