"""Non-persistent identifier allocation endpoint.

Mints a workspace-identity artifact ID for a diagram entity before the diagram is
saved. The prefix is resolved from the entity-type's ``id_prefix`` metadata —
callers cannot supply an arbitrary prefix.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from src.application.identifier_allocator import get_default_allocator
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.routers._openapi import TAG_ENTITIES, OpenMapResponse

router = APIRouter()


class _AllocateRequest:
    def __init__(
        self,
        diagram_type: str = Body(...),
        entity_type: str = Body(...),
        name_hint: str | None = Body(default=None),
        owner_kind: str = Body(default="diagram"),
    ) -> None:
        self.diagram_type = diagram_type
        self.entity_type = entity_type
        self.name_hint = name_hint
        self.owner_kind = owner_kind


@router.post("/api/identifiers/allocate", tags=[TAG_ENTITIES], summary="Allocate artifact identifiers",
    response_model=OpenMapResponse)
def allocate_identifier(
    diagram_type: Annotated[str, Body()],
    entity_type: Annotated[str, Body()],
    name_hint: Annotated[str | None, Body()] = None,
    owner_kind: Annotated[str, Body()] = "diagram",
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, str]:
    """Mint a workspace-identity ID for a diagram entity (non-persistent).

    The prefix is resolved from the entity-type's ``id_prefix`` metadata registered
    in the diagram-type module. Caller-supplied prefixes are never accepted.

    Returns ``{"id": "CLF@epoch.random.slug"}`` for a ``classifier`` entity type.
    """
    dt_module = catalogs.diagram_types.find_diagram_type(diagram_type)
    if dt_module is None:
        raise HTTPException(404, f"Unknown diagram type: {diagram_type!r}")

    ui_entry = next(
        (oe for oe in dt_module.ui_config.diagram_only_types if oe.entity_type == entity_type),
        None,
    )
    if ui_entry is None:
        raise HTTPException(
            400, f"Entity type {entity_type!r} is not a diagram-owned type of {diagram_type!r}"
        )
    if ui_entry.identity_scope != "workspace":
        raise HTTPException(
            400,
            f"Entity type {entity_type!r} has identity_scope {ui_entry.identity_scope!r}; "
            f"only workspace-scoped types can use this endpoint",
        )
    if not ui_entry.id_prefix:
        raise HTTPException(
            500, f"Entity type {entity_type!r} has no id_prefix declared in its ontology"
        )

    allocator = get_default_allocator()
    new_id = allocator.allocate(prefix=ui_entry.id_prefix, name_hint=name_hint)
    return {"id": new_id}
