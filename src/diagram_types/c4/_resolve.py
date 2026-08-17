"""C4 state resolution: model-backed (ArchiMate graph) and standalone (explicit entities)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Re-export shared types so existing imports from this module continue to work.
from src.diagram_types.c4._c4_types import (  # noqa: F401
    _alias_for,
    _C4Connection,
    _normalize_alias,
    _ResolvedItem,
    _ResolvedState,
)
from src.diagram_types.c4._resolve_model import resolve_model_backed
from src.domain.diagrams.bindings import SCOPE_IDS_KEY, SCOPE_KEY
from src.domain.diagrams.diagram_selection import DiagramSelectionError


def scope_ids_in(diagram_entities: Mapping[str, object]) -> tuple[str, ...]:
    """The scope this diagram's entities declare in shorthand, singular or set.

    The renderer sees the shorthand rather than the canonical binding, because the write path puts
    it back before rendering (`render_entities_restored`). One reading of the pair of keys, so
    the resolver and the navigation cannot disagree about which one a diagram carries.
    """
    single = str(diagram_entities.get(SCOPE_KEY) or "").strip()
    if single:
        return (single,)
    raw = diagram_entities.get(SCOPE_IDS_KEY)
    if isinstance(raw, list):
        return tuple(cleaned for item in raw if (cleaned := str(item).strip()))
    return ()


def resolve_c4_state(
    config: dict[str, Any],
    diagram_type: str,
    repo_root: Path,
    diagram_entities: Mapping[str, object],
    diagram_connections: list[dict[str, object]],
    person_archimate_types: frozenset[str],
) -> _ResolvedState:
    scope_entity_ids = scope_ids_in(diagram_entities)
    c4_cfg = _c4_settings(config)
    scope_entity_type = str(c4_cfg["scope_entity_type"])
    scope_render_mode = str(c4_cfg["scope_render_mode"])
    internal_types = [str(t) for t in (c4_cfg.get("internal_entity_types") or [])]
    internal_c4_type = internal_types[0] if internal_types else "container"

    if scope_entity_ids:
        return resolve_model_backed(
            diagram_type, repo_root, diagram_entities, scope_entity_ids,
            scope_entity_type, scope_render_mode, internal_c4_type, person_archimate_types,
            technology_attributes=[str(a) for a in (c4_cfg.get("technology_attributes") or [])],
            technology_limit=int(c4_cfg.get("technology_max_entries") or 0),
        )
    return _resolve_standalone(
        diagram_type, diagram_entities, diagram_connections,
        scope_entity_type, scope_render_mode, frozenset(internal_types),
    )


def _resolve_standalone(
    diagram_type: str,
    diagram_entities: Mapping[str, object],
    diagram_connections: list[dict[str, object]],
    scope_entity_type: str,
    scope_render_mode: str,
    internal_types: frozenset[str],
) -> _ResolvedState:
    items = _items_from_diagram_entities(diagram_entities)

    if not items:
        placeholder = _ResolvedItem(
            local_id="_blank", item_type=scope_entity_type,
            alias="C4_blank", label="(add entities to get started)",
            description="", technology="", external=False,
        )
        return _ResolvedState(
            scope_items=(placeholder,), scope_render_mode=scope_render_mode,
            internal_items=[], outside_items=[], connections=(),
            entity_ids=(), connection_artifact_ids=(),
        )

    scope_items_of_type = [i for i in items if i.item_type == scope_entity_type]
    if not scope_items_of_type:
        raise DiagramSelectionError(
            f"{diagram_type!r} (standalone): needs at least one '{scope_entity_type}' item"
        )

    raw_scope_marked = _scope_marked_id(diagram_entities, scope_entity_type)
    scope_item = next(
        (i for i in scope_items_of_type if i.local_id == raw_scope_marked),
        scope_items_of_type[0],
    )

    internal_items = [
        i for i in items
        if i.local_id != scope_item.local_id and not i.external and i.item_type in internal_types
    ]
    outside_items = [
        i for i in items
        if i.local_id != scope_item.local_id and i not in internal_items
    ]

    alias_by_lid = {i.local_id: i.alias for i in items}
    connections = tuple(
        _C4Connection(
            src_alias=alias_by_lid[str(dc.get("source") or "")],
            tgt_alias=alias_by_lid[str(dc.get("target") or "")],
            label=str(dc.get("label") or ""),
        )
        for dc in diagram_connections
        if isinstance(dc, dict)
        and str(dc.get("source") or "") in alias_by_lid
        and str(dc.get("target") or "") in alias_by_lid
    )

    return _ResolvedState(
        scope_items=(scope_item,),
        scope_render_mode=scope_render_mode,
        internal_items=internal_items,
        outside_items=outside_items,
        connections=connections,
        entity_ids=(),
        connection_artifact_ids=(),
    )


def _items_from_diagram_entities(diagram_entities: Mapping[str, object]) -> list[_ResolvedItem]:
    items: list[_ResolvedItem] = []
    for item_type, raw_list in diagram_entities.items():
        if not isinstance(raw_list, list):
            continue
        for index, raw in enumerate(raw_list):
            if not isinstance(raw, Mapping):
                continue
            local_id = str(raw.get("id") or "").strip()
            if not local_id:
                continue
            entity_id = str(raw.get("entity_id") or "").strip() or None
            label = str(raw.get("label") or local_id)
            alias = _normalize_alias(str(raw.get("alias") or "")) or _alias_for(item_type, local_id, index)
            shape_raw = str(raw.get("shape") or "").strip()
            items.append(_ResolvedItem(
                local_id=local_id,
                item_type=str(item_type),
                alias=alias,
                label=label,
                description=str(raw.get("description") or ""),
                technology=str(raw.get("technology") or ""),
                external=bool(raw.get("external", False)),
                entity_id=entity_id,
                shape=shape_raw or None,
            ))
    return items


def _scope_marked_id(diagram_entities: Mapping[str, object], scope_entity_type: str) -> str | None:
    raw_list: object = diagram_entities.get(scope_entity_type)
    if not isinstance(raw_list, list):
        return None
    for raw in raw_list:
        if isinstance(raw, Mapping) and raw.get("scope") and raw.get("id"):
            return str(raw["id"])
    return None


def _c4_settings(config: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = config.get("c4")
    if not isinstance(raw, Mapping):
        raise ValueError("C4 config must define a 'c4' mapping")
    if not raw.get("scope_entity_type"):
        raise ValueError("C4 config must define c4.scope_entity_type")
    if not raw.get("scope_render_mode"):
        raise ValueError("C4 config must define c4.scope_render_mode")
    return raw
