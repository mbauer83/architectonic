"""Helpers for extracting diagram-only EntityRecords and ConnectionRecords from frontmatter.

Supports both canonical 'id'-keyed formats (activity, C4) and 'node_id'-keyed formats (GSN).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping

from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord

_ID_KEYS: frozenset[str] = frozenset({"id", "node_id", "source_id", "target_id"})


def _diagram_local_id(item: dict[str, object]) -> str:
    """Return the canonical local ID for a diagram-entity item, checking 'id' then 'node_id'."""
    return str(item.get("id") or item.get("node_id") or "")


def _is_connection_item(item: dict[str, object]) -> bool:
    """True if this item looks like a connection (has source/target) but not an entity (no id/node_id)."""
    return bool(
        not _diagram_local_id(item)
        and (item.get("source") or item.get("source_id"))
        and (item.get("target") or item.get("target_id"))
        and item.get("conn_type")
    )


def _leaf_strings(value: object) -> Iterator[str]:
    """Yield every non-empty leaf string in *value*, descending lists/dicts, skipping ID keys."""
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, list):
        for v in value:
            yield from _leaf_strings(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in _ID_KEYS:
                yield from _leaf_strings(v)


def _diagram_entity_content_text(item: dict[str, object]) -> str:
    """Collect leaf string values for FTS (skip ID-role fields)."""
    return " ".join(_leaf_strings({k: v for k, v in item.items() if k not in _ID_KEYS}))


def diagram_bound_entity_ids(extra: Mapping[str, object]) -> list[str]:
    """Workspace entity ids a diagram binds or links to via its frontmatter.

    Covers the matrix axes (``from-entity-ids``/``to-entity-ids``) and C4 ``bindings``
    (``target.entity_id``). Diagram-local nodes are not included here — their names are
    resolved separately via ``host_diagram_id``.
    """
    ids: list[str] = []
    for axis_key in ("from-entity-ids", "to-entity-ids"):
        axis = extra.get(axis_key)
        if isinstance(axis, list):
            ids.extend(v for v in axis if isinstance(v, str) and v)
    bindings = extra.get("bindings")
    if isinstance(bindings, list):
        for binding in bindings:
            target = binding.get("target") if isinstance(binding, dict) else None
            if not isinstance(target, dict):
                continue
            entity_id = target.get("entity_id")
            if isinstance(entity_id, str) and entity_id:
                ids.append(entity_id)
            entity_ids = target.get("entity_ids")
            if isinstance(entity_ids, list):
                ids.extend(v for v in entity_ids if isinstance(v, str) and v)
    return ids


def diagram_member_text(
    diag: DiagramRecord,
    *,
    local_names: Iterable[str],
    name_of: Callable[[str], str | None],
) -> str:
    """Space-joined, de-duplicated names of the entities a diagram contains or links to.

    ``local_names`` are the names of diagram-local entities (resolved by the caller from
    ``host_diagram_id``); bound workspace entities are resolved via ``name_of``. The
    result feeds the diagram FTS index so a diagram is discoverable by its members' names.
    """
    bound_names = (name_of(entity_id) for entity_id in diagram_bound_entity_ids(diag.extra))
    seen: set[str] = set()
    ordered: list[str] = []
    for name in (*local_names, *(n for n in bound_names if n)):
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return " ".join(ordered)


def extract_diagram_entities(
    diag: DiagramRecord,
    workspace_entity_types: frozenset[str] = frozenset(),
) -> list[EntityRecord]:
    """Extract diagram-only EntityRecords from a diagram's diagram-entities frontmatter.

    Recognises both canonical 'id' and diagram-specific 'node_id' (GSN format).
    Sets display_alias to the local_id so SVG alias matching works.
    Skips connection-like items (those with source/target but no id/node_id).

    For entity types in *workspace_entity_types* the artifact_id is the bare local_id
    (a canonical ``CLF@epoch.random.slug``); otherwise it is the qualified
    ``{diagram_id}#{entity_type}/{local_id}`` form.  ``host_diagram_id`` is always set
    to the owning diagram for both scopes.
    """
    diagram_entities = diag.extra.get("diagram-entities")
    if not isinstance(diagram_entities, dict):
        return []
    result: list[EntityRecord] = []
    for entity_type, items in diagram_entities.items():
        if not isinstance(items, list):
            continue
        is_workspace = entity_type in workspace_entity_types
        for item in items:
            if not isinstance(item, dict):
                continue
            if _is_connection_item(item):
                continue
            local_id = _diagram_local_id(item)
            if not local_id:
                continue
            artifact_id = local_id if is_workspace else f"{diag.artifact_id}#{entity_type}/{local_id}"
            name = str(item.get("label") or item.get("text") or item.get("name") or local_id)
            content_text = _diagram_entity_content_text(item)
            result.append(
                EntityRecord(
                    artifact_id=artifact_id,
                    artifact_type=entity_type,
                    name=name,
                    version=diag.version,
                    status=diag.status,
                    domain=diag.diagram_type,
                    subdomain=entity_type,
                    path=diag.path,
                    keywords=(),
                    extra={k: v for k, v in item.items() if not isinstance(v, list)},
                    content_text=content_text,
                    display_blocks={},
                    display_label=name,
                    display_alias=local_id,
                    host_diagram_id=diag.artifact_id,
                )
            )
    return result


def diagram_local_to_full(
    diag: DiagramRecord,
    workspace_entity_types: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Map each diagram-entity local id to its canonical artifact_id.

    For workspace-scoped entity types, the local_id IS the canonical id.
    For diagram-scoped entity types, the canonical id is ``{diagram_id}#{entity_type}/{local_id}``.
    """
    diagram_entities = diag.extra.get("diagram-entities")
    if not isinstance(diagram_entities, dict):
        return {}
    result: dict[str, str] = {}
    for entity_type, items in diagram_entities.items():
        if not isinstance(items, list):
            continue
        is_workspace = entity_type in workspace_entity_types
        for item in items:
            if not isinstance(item, dict):
                continue
            local_id = _diagram_local_id(item)
            if not local_id:
                continue
            result[local_id] = local_id if is_workspace else f"{diag.artifact_id}#{entity_type}/{local_id}"
    return result


def _diagram_connection_record(
    kc: object, diag: DiagramRecord, local_to_full: dict[str, str]
) -> ConnectionRecord | None:
    """Build one ConnectionRecord from a connection row, or None if incomplete.

    Accepts both canonical 'source'/'target' and GSN-style 'source_id'/'target_id'.
    Generates a stable local_id from endpoints when no explicit 'id' is given.
    """
    if not isinstance(kc, dict):
        return None
    conn_type = str(kc.get("conn_type") or "")
    source_local = str(kc.get("source") or kc.get("source_id") or "")
    target_local = str(kc.get("target") or kc.get("target_id") or "")
    if not (conn_type and source_local and target_local):
        return None
    local_id = str(kc.get("id") or f"{source_local}:{conn_type}:{target_local}")
    return ConnectionRecord(
        artifact_id=f"{diag.artifact_id}#conn/{local_id}",
        source=local_to_full.get(source_local, f"{diag.artifact_id}#unknown/{source_local}"),
        target=local_to_full.get(target_local, f"{diag.artifact_id}#unknown/{target_local}"),
        conn_type=conn_type,
        version=diag.version,
        status=diag.status,
        path=diag.path,
        extra={},
        content_text="",
    )


def extract_diagram_connections(
    diag: DiagramRecord,
    workspace_entity_types: frozenset[str] = frozenset(),
) -> list[ConnectionRecord]:
    """Extract ConnectionRecords from diagram frontmatter.

    Two sources are checked:
    1. Top-level 'connections' key (canonical format).
    2. Connection-like items inside 'diagram-entities' sub-keys (GSN/assurance format
       where edges sit alongside nodes under 'diagram-entities').

    Each source/target local ID is resolved via diagram_local_to_full.
    """
    local_to_full = diagram_local_to_full(diag, workspace_entity_types)
    result: list[ConnectionRecord] = []

    diagram_connections = diag.extra.get("connections")
    if isinstance(diagram_connections, list):
        for kc in diagram_connections:
            rec = _diagram_connection_record(kc, diag, local_to_full)
            if rec is not None:
                result.append(rec)

    diagram_entities = diag.extra.get("diagram-entities")
    if isinstance(diagram_entities, dict):
        for items in diagram_entities.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and _is_connection_item(item):
                    rec = _diagram_connection_record(item, diag, local_to_full)
                    if rec is not None:
                        result.append(rec)

    return result
