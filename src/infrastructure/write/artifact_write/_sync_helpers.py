"""Private inference helpers for diagram-to-model sync (ArchiMate reconcile path).

All symbols here are consumed by diagram_sync.py only.
"""

from __future__ import annotations

import re
from typing import Protocol

from src.application.artifacts.parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.application.puml_relation_parsing import declared_relations
from src.application.read_models import EntityContextConnection
from src.domain.artifact_id import (
    ConnectionReference,
    parse_connection_reference,
)
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.app_bootstrap import process_runtime_catalogs


class LookupStore(Protocol):
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...
    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...
    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]: ...
    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
    ) -> list[ConnectionRecord]: ...
    #: What the model connects a set of entities with. Declared here rather than reached for through
    #: `list_connections` and a filter written again: `connections_among` already owns that
    #: question, and answering it a second way is how two callers come to disagree about what a
    #: diagram of a set of entities draws.
    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]: ...


_STD_ALIAS_RE = re.compile(r"^(?P<prefix>[A-Z]{2,6})_(?P<random>[A-Za-z0-9_-]{4,})$")


def stable_prefix(artifact_id: str) -> str:
    """Return the rename-stable part of an artifact ID (drops the trailing slug)."""
    return artifact_id.rsplit(".", 1)[0]


def resolve_entities(
    ids: list[str],
    store: LookupStore,
) -> tuple[list[EntityRecord], list[str]]:
    """Resolve entity IDs to records, following renames via stable-prefix fallback.

    Returns (resolved_records, removed_ids).
    """
    by_prefix: dict[str, EntityRecord] = {stable_prefix(e.artifact_id): e for e in store.list_entities()}
    records: list[EntityRecord] = []
    removed: list[str] = []
    for eid in ids:
        record = store.get_entity(eid)
        if record is None:
            record = by_prefix.get(stable_prefix(eid))
        if record is not None:
            records.append(record)
        else:
            removed.append(eid)
    return records, removed


def resolve_connections(
    ids: list[str],
    store: LookupStore,
) -> tuple[list[ConnectionRecord], list[str]]:
    """Resolve connection IDs to records, following renames via stable-prefix fallback."""
    connections = store.list_connections()
    by_prefix: dict[str, ConnectionRecord] = {stable_prefix(c.artifact_id): c for c in connections}
    records: list[ConnectionRecord] = []
    removed: list[str] = []
    for cid in ids:
        record = store.get_connection(cid)
        if record is None:
            record = by_prefix.get(stable_prefix(cid))
        if record is None:
            record = resolve_connection_by_parts(cid, connections)
        if record is not None:
            records.append(record)
        else:
            removed.append(cid)
    return records, removed


def parse_connection_artifact_id(artifact_id: str) -> ConnectionReference | None:
    """Both naming forms, through the domain grammar that owns them.

    Byte-identical to a second copy in `bulk/diagram_refs` and field-transposed against a third in
    `_promote_planning`; all three now call one reading.
    """
    return parse_connection_reference(artifact_id)


def resolve_connection_by_parts(
    artifact_id: str,
    connections: list[ConnectionRecord],
) -> ConnectionRecord | None:
    parsed = parse_connection_artifact_id(artifact_id)
    if parsed is None:
        return None
    source_prefix = stable_prefix(parsed.source)
    target_prefix = stable_prefix(parsed.target)
    for record in connections:
        if record.conn_type != parsed.conn_type:
            continue
        if stable_prefix(record.source) == source_prefix and stable_prefix(record.target) == target_prefix:
            return record
    return None


def _normalize_standard_alias(artifact_id: str) -> str:
    parts = artifact_id.split(".")
    if len(parts) < 2 or "@" not in parts[0]:
        return ""
    prefix = parts[0].split("@", 1)[0]
    return f"{prefix}_{parts[1]}"


def _resolve_standard_alias(alias: str, entities: list[EntityRecord]) -> EntityRecord | None:
    match = _STD_ALIAS_RE.match(alias)
    if match is None:
        return None
    prefix = match.group("prefix")
    random = match.group("random")
    needle = f".{random}."
    for entity in entities:
        if entity.artifact_id.startswith(f"{prefix}@") and needle in entity.artifact_id:
            return entity
    return None


def alias_entity_lookup(store: LookupStore) -> dict[str, EntityRecord]:
    alias_map: dict[str, EntityRecord] = {}
    entities = store.list_entities()
    for entity in entities:
        if entity.display_alias:
            alias_map.setdefault(normalize_puml_alias(entity.display_alias), entity)
        std_alias = _normalize_standard_alias(entity.artifact_id)
        if std_alias:
            alias_map.setdefault(normalize_puml_alias(std_alias), entity)
    return alias_map


def infer_entities_from_puml(
    puml_body: str,
    store: LookupStore,
) -> tuple[list[EntityRecord], list[str]]:
    alias_map = alias_entity_lookup(store)
    inferred: list[EntityRecord] = []
    unresolved_aliases: list[str] = []
    seen: set[str] = set()
    for alias in sorted(extract_declared_puml_aliases(puml_body)):
        normalized = normalize_puml_alias(alias)
        record = alias_map.get(normalized)
        if record is None:
            record = _resolve_standard_alias(normalized, store.list_entities())
        if record is None:
            unresolved_aliases.append(alias)
            continue
        if record.artifact_id in seen:
            continue
        seen.add(record.artifact_id)
        inferred.append(record)
    return inferred, unresolved_aliases


def stereotype_to_connection_type() -> dict[str, str]:

    return dict(
        process_runtime_catalogs().ontology.archimate_stereotype_to_connection_type()
    )


def resolve_untyped_relation(
    src_id: str,
    tgt_id: str,
    arrow: str,
    connections: list[ConnectionRecord],
) -> ConnectionRecord | None:
    """The model connection a bare arrow between two entities denotes, or None if undecidable.

    A bare arrow names its endpoints but not its type, and the glyph cannot supply one: ``..>`` is
    the declared ``puml_arrow`` of both ``archimate-access`` and ``archimate-influence``. So the
    model decides — for almost every pair there is exactly one connection, and the arrow is it.
    Where a pair carries several, the drawn glyph breaks the tie if it matches exactly one of their
    declared arrows. Still ambiguous means None: binding the wrong relation would silently rewrite
    what the diagram asserts, which is worse than reporting it unresolved.
    """
    candidates = [c for c in connections if c.source == src_id and c.target == tgt_id]
    if not candidates:
        candidates = [
            c for c in connections
            if c.source == tgt_id and c.target == src_id and _is_bidirectional(c.conn_type)
        ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    if not arrow:
        # Stated by nesting rather than by an arrow: PlantUML draws containment that way, so among
        # several connections between the pair the containment one is what the nesting asserts.
        nesting = [c for c in candidates if _is_nesting(c.conn_type)]
        return nesting[0] if len(nesting) == 1 else None
    by_arrow = [c for c in candidates if _declared_arrow(c.conn_type) == arrow]
    return by_arrow[0] if len(by_arrow) == 1 else None


def _connection_type_info(conn_type: str):  # type: ignore[no-untyped-def]
    from src.domain.modules.module_types import ConnectionTypeName  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

    return get_module_registry().find_connection_type(ConnectionTypeName(conn_type))


def _is_bidirectional(conn_type: str) -> bool:
    info = _connection_type_info(conn_type)
    return bool(info is not None and info.bidirectional_sync)


def _is_nesting(conn_type: str) -> bool:
    """True for the containment relations PlantUML renders as nesting (composition, aggregation)."""
    info = _connection_type_info(conn_type)
    return bool(info is not None and "nesting" in tuple(getattr(info, "classes", ()) or ()))


def _declared_arrow(conn_type: str) -> str:
    info = _connection_type_info(conn_type)
    return str(getattr(info, "puml_arrow", "") or "") if info is not None else ""


def resolve_relation_connection(
    src_id: str,
    tgt_id: str,
    conn_type: str,
    connections: list[ConnectionRecord],
) -> ConnectionRecord | None:
    direct = resolve_connection_by_parts(f"{src_id}---{tgt_id}@@{conn_type}", connections)
    if direct is not None:
        return direct
    from src.domain.modules.module_types import ConnectionTypeName  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

    ct_info = get_module_registry().find_connection_type(ConnectionTypeName(conn_type))
    if ct_info is not None and ct_info.bidirectional_sync:
        return resolve_connection_by_parts(f"{tgt_id}---{src_id}@@{conn_type}", connections)
    return None


def infer_connections_from_puml(
    puml_body: str,
    store: LookupStore,
) -> tuple[list[ConnectionRecord], list[str]]:
    """Connections the body draws, resolved against the model, plus the ones that would be lost.

    Reads every form a body can state a relation in — including the bare arrows the renderer
    actually emits, which this used to ignore entirely. Ignoring them meant a generated body
    contributed nothing back to its own binding set, so any relation drawn but unbound was deleted
    by the next refresh without appearing in the removed list.
    """
    alias_map = alias_entity_lookup(store)
    all_connections = store.list_connections()
    stereo_map = stereotype_to_connection_type()
    inferred: list[ConnectionRecord] = []
    removed: list[str] = []
    seen: set[str] = set()

    for relation in declared_relations(puml_body, stereo_map):
        src = alias_map.get(normalize_puml_alias(relation.source_alias))
        tgt = alias_map.get(normalize_puml_alias(relation.target_alias))
        if src is None or tgt is None:
            continue
        record = (
            resolve_relation_connection(src.artifact_id, tgt.artifact_id, relation.connection_type, all_connections)
            if relation.connection_type is not None
            else resolve_untyped_relation(src.artifact_id, tgt.artifact_id, relation.arrow, all_connections)
        )
        if record is None:
            removed.append(
                f"{src.artifact_id}---{tgt.artifact_id}@@{relation.connection_type or 'unresolved'}"
            )
            continue
        if record.artifact_id in seen:
            continue
        seen.add(record.artifact_id)
        inferred.append(record)
    return inferred, removed


def dedupe_entities(records: list[EntityRecord]) -> list[EntityRecord]:
    out: list[EntityRecord] = []
    seen: set[str] = set()
    for record in records:
        if record.artifact_id in seen:
            continue
        seen.add(record.artifact_id)
        out.append(record)
    return out


def dedupe_connections(records: list[ConnectionRecord]) -> list[ConnectionRecord]:
    out: list[ConnectionRecord] = []
    seen: set[str] = set()
    for record in records:
        if record.artifact_id in seen:
            continue
        seen.add(record.artifact_id)
        out.append(record)
    return out
