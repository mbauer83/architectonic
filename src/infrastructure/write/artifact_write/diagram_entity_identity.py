"""Normalize workspace-identity entity IDs in a diagram payload.

Provides ``normalize_diagram_entity_identities``, which allocates canonical
workspace IDs (e.g. ``CLF@epoch.random.slug``) for diagram entities that carry
a temp/missing ID, then rewrites all references atomically — the entity ID field,
connection source/target endpoints, binding entity references, and any nested
classifier references in entity attributes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.application.identifier_allocator import IdentifierAllocator
    from src.domain.modules.catalogs import DiagramTypeCatalog

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


def _is_valid_workspace_id(value: str, *, prefix: str) -> bool:
    return bool(re.match(rf"^{re.escape(prefix)}@[0-9]+\.[A-Za-z0-9_-]+\..+$", value))


def _replace_ids(obj: Any, id_map: dict[str, str]) -> Any:
    """Recursively replace every string value that is a key in id_map."""
    if isinstance(obj, str):
        return id_map.get(obj, obj)
    if isinstance(obj, list):
        return [_replace_ids(v, id_map) for v in obj]
    if isinstance(obj, dict):
        return {k: _replace_ids(v, id_map) for k, v in obj.items()}
    return obj


def normalize_diagram_entity_identities(
    diagram_type: str,
    diagram_entities: dict[str, list[dict[str, Any]]],
    diagram_connections: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    *,
    module_catalog: "DiagramTypeCatalog",
    allocator: "IdentifierAllocator",
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Allocate workspace IDs for diagram entities that lack a valid one.

    For each entity type with ``identity_scope: workspace``, any entity item whose
    ``id`` field is missing or does not match the expected grammar receives a freshly
    allocated ID. After building the old→new ID map, all three payload parts are
    rewritten atomically: entity IDs, connection source/target endpoints, binding
    references, and any nested classifier references inside entity attributes.

    Returns ``(diagram_entities, diagram_connections, bindings)`` with all IDs
    normalized. Entities with already-valid IDs are left unchanged.
    """
    dt_module = module_catalog.find_diagram_type(diagram_type)
    if dt_module is None:
        return diagram_entities, diagram_connections, bindings

    workspace_types: dict[str, str] = {
        oe.entity_type: oe.id_prefix
        for oe in dt_module.ui_config.diagram_only_types
        if oe.identity_scope == "workspace" and oe.id_prefix
    }
    if not workspace_types:
        return diagram_entities, diagram_connections, bindings

    id_map: dict[str, str] = {}
    new_entities: dict[str, list[dict[str, Any]]] = {}

    for entity_type, items in diagram_entities.items():
        prefix = workspace_types.get(entity_type)
        if prefix is None:
            new_entities[entity_type] = items
            continue

        rewritten: list[dict[str, Any]] = []
        for item in items:
            old_id = str(item.get("id") or "")
            if old_id and _is_valid_workspace_id(old_id, prefix=prefix):
                rewritten.append(item)
            else:
                name_hint = str(item.get("label") or item.get("name") or old_id or "")
                new_id = allocator.allocate(prefix=prefix, name_hint=name_hint or None)
                id_map[old_id] = new_id
                rewritten.append({**item, "id": new_id})
        new_entities[entity_type] = rewritten

    if not id_map:
        return diagram_entities, diagram_connections, bindings

    new_connections = _replace_ids(diagram_connections, id_map)
    new_bindings = _replace_ids(bindings, id_map)
    final_entities = _replace_ids(new_entities, id_map)

    return final_entities, new_connections, new_bindings
