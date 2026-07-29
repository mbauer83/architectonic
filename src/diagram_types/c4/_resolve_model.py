"""C4 model-backed state resolution (ArchiMate graph → C4 items/connections)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.diagram_types.c4._c4_types import (
    _alias_for,
    _C4Connection,
    _conn_label,
    _normalize_alias,
    _ResolvedItem,
    _ResolvedState,
)


def _short_description(entity: Any) -> str:
    """First prose sentence of the entity's body, ≤100 chars — the C4 element role line.

    Skips the leading ``## Name`` heading and any table/properties blocks; returns the
    first real paragraph's opening sentence so C4 persons carry a short role description.
    """
    text = getattr(entity, "content_text", "") if entity is not None else ""
    if not text:
        return ""
    for block in text.split("\n\n"):
        line = block.strip().splitlines()[0].strip() if block.strip() else ""
        if not line or line.startswith(("#", "|", "-", "*", ">")):
            continue
        sentence = line.split(". ")[0].rstrip(".")
        return sentence if len(sentence) <= 100 else sentence[:99].rstrip() + "…"
    return ""


def _item_from_entity(entity: Any, entity_id: str, item_type: str, *, external: bool) -> _ResolvedItem:
    label = entity.name if entity is not None else entity_id
    raw_alias = getattr(entity, "display_alias", "") or "" if entity is not None else ""
    alias = _normalize_alias(raw_alias) if raw_alias else _alias_for(item_type, entity_id)
    return _ResolvedItem(
        local_id=entity_id,
        item_type=item_type,
        alias=alias,
        label=label,
        description=_short_description(entity),
        technology="",
        external=external,
        shape=None,  # model-backed items use technology inference
    )


def resolve_model_backed(
    diagram_type: str,
    repo_root: Path,
    diagram_entities: Mapping[str, object],
    scope_entity_id: str,
    scope_entity_type: str,
    scope_render_mode: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
) -> _ResolvedState:
    from src.diagram_types.c4._projection import project_c4  # noqa: PLC0415
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    query = shared_artifact_index([repo_root])
    scope_entity = query.get_entity(scope_entity_id)
    if scope_entity is None:
        raise ValueError(f"{diagram_type!r}: scope entity {scope_entity_id!r} not found")

    projection = project_c4(
        diagram_type, scope_entity_id, query,
        internal_c4_type=internal_c4_type,
        scope_entity_type=scope_entity_type,
        person_archimate_types=person_archimate_types,
    )

    raw_included = diagram_entities.get("_included_entity_ids")
    raw_excluded = diagram_entities.get("_excluded_entity_ids")
    included_only: set[str] | None = None
    excluded_ids: set[str] = set()
    if isinstance(raw_included, list) and raw_included:
        included_only = {str(x) for x in raw_included}
    elif isinstance(raw_excluded, list) and raw_excluded:
        excluded_ids = {str(x) for x in raw_excluded}

    scope_item = _item_from_entity(scope_entity, scope_entity_id, scope_entity_type, external=False)
    internal_items: list[_ResolvedItem] = []
    outside_items: list[_ResolvedItem] = []

    for proj_item in projection.items:
        if proj_item.role == "scope":
            continue
        eid = proj_item.entity_id
        if included_only is not None and eid not in included_only:
            continue
        if eid in excluded_ids:
            continue
        entity = query.get_entity(eid)
        if entity is None:
            continue
        resolved = _item_from_entity(entity, eid, proj_item.item_type, external=(proj_item.role == "external"))
        if proj_item.role == "internal":
            internal_items.append(resolved)
        else:
            outside_items.append(resolved)

    # Additive validated inclusion — extra IDs in _included_entity_ids that the
    # projection did not yield are added as external neighbours if graph-justified.
    if included_only:
        projected_eids = {scope_entity_id} | {i.local_id for i in internal_items} | {i.local_id for i in outside_items}
        for extra_eid in sorted(included_only - projected_eids):
            entity = query.get_entity(extra_eid)
            if entity is None:
                continue
            if any(
                c.source in projected_eids or c.target in projected_eids
                for c in query.find_connections_for(extra_eid, direction="any")
            ):
                outside_items.append(_item_from_entity(entity, extra_eid, "software-system", external=True))

    all_displayed = (
        {scope_entity_id}
        | {i.local_id for i in internal_items}
        | {i.local_id for i in outside_items}
    )
    alias_by_eid = {i.local_id: i.alias for i in [scope_item, *internal_items, *outside_items]}

    model_conns: list[Any] = []
    for cid in projection.connection_ids:
        conn = query.get_connection(cid)
        if conn is None:
            continue
        if conn.source not in all_displayed and conn.target not in all_displayed:
            continue
        model_conns.append(conn)
    model_conns.sort(key=lambda x: x.artifact_id)

    # Build the C4 edge list with direction normalisation and deduplication.
    is_ctx = (diagram_type == "c4-system-context")
    scope_alias = alias_by_eid.get(scope_entity_id, "")
    provider_aliases = {scope_alias} | {i.alias for i in internal_items}
    seen_pairs: set[tuple[str, str]] = set()
    conn_list: list[_C4Connection] = []
    for c in model_conns:
        src = alias_by_eid.get(c.source) or (scope_alias if is_ctx else None)
        tgt = alias_by_eid.get(c.target) or (scope_alias if is_ctx else None)
        if src is None or tgt is None:
            continue
        if c.conn_type == "archimate-serving":
            src, tgt = tgt, src
        elif c.conn_type == "archimate-association" and src in provider_aliases and tgt not in provider_aliases:
            src, tgt = tgt, src
        if src == tgt:
            continue
        pair = (src, tgt)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        conn_list.append(_C4Connection(
            src_alias=src, tgt_alias=tgt,
            label=_conn_label(c),
            artifact_id=c.artifact_id,
        ))

    return _ResolvedState(
        scope_item=scope_item,
        scope_render_mode=scope_render_mode,
        internal_items=internal_items,
        outside_items=outside_items,
        connections=tuple(conn_list),
        entity_ids=tuple(sorted(all_displayed)),
        connection_artifact_ids=tuple(c.artifact_id for c in model_conns),
    )
