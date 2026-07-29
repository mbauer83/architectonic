"""Module registry discovery endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.routers._openapi import TAG_TAXONOMY, OpenMapResponse

router = APIRouter()


@router.get("/api/modules", tags=[TAG_TAXONOMY], summary="Loaded ontology / diagram-type modules",
    response_model=list[OpenMapResponse])
def list_modules(catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency)) -> list[dict[str, object]]:
    """Return metadata for every registered (enabled + satisfied) ontology module."""
    return [
        {
            "name": om.name,
            "module_class": om.module_class,
            "enabled": bool(getattr(om, "enabled", True)),
            "requires": list(getattr(om, "requires", [])),
            "entity_type_count": len(om.entity_types),
            "connection_type_count": len(om.connection_types),
        }
        for om in sorted(catalogs.module_catalog.all_ontologies().values(), key=lambda m: m.name)
    ]
