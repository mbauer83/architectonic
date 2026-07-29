"""C19C v3.1 model-exchange import use case (D10, parent plan §4.5, WU-F3a).

Applies the Appendix E.4 migration table (via ``ExchangeConceptMapper``) to every element
and relationship in a parsed ``ExchangeModel``, writing through ``ExchangeArtifactWriter``
(the same ``artifact_write`` validation path as the GUI/MCP). Dry-run by default; nothing
is written until the caller passes ``commit=True``. Re-import is idempotent: the injected
``ExchangeIdentityStore`` remembers each element's ``exchange_id -> artifact_id`` mapping
(recorded only on commit), so a second import of the same document updates existing
entities instead of duplicating them; connection identity is already derived
deterministically from (source, target, connection_type), so once the two endpoints
resolve to the same artifact ids again, the connection resolves to the same artifact id
too and is skipped rather than duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.application.exchange.concept_mapping import ExchangeConceptMapper, UnmappableConceptError
from src.application.exchange.document import (
    ExchangeElement,
    ExchangeModel,
    ExchangeProperty,
    ExchangeRelationship,
    LangString,
)
from src.application.exchange.identity_store import ExchangeIdentityStore
from src.application.exchange.read_ports import ConnectionLookup
from src.application.exchange.write_ports import ExchangeArtifactWriter, InvalidRelationshipError

_SPECIALIZATION_HINT_KEY = "archrepo-specialization"
_RESERVED_PROPERTY_PREFIX = "archrepo-"


@dataclass(frozen=True)
class ImportedEntity:
    exchange_id: str
    artifact_id: str
    name: str
    action: Literal["created", "updated"]
    warning: str | None = None


@dataclass(frozen=True)
class ImportedConnection:
    exchange_id: str
    artifact_id: str
    action: Literal["created", "skipped"]
    warning: str | None = None


@dataclass(frozen=True)
class UnmappableItem:
    exchange_id: str
    kind: Literal["element", "relationship"]
    concept_type: str
    reason: str


@dataclass(frozen=True)
class ImportReport:
    committed: bool
    entities: tuple[ImportedEntity, ...] = ()
    connections: tuple[ImportedConnection, ...] = ()
    unmappable: tuple[UnmappableItem, ...] = ()


def _primary_text(strings: tuple[LangString, ...]) -> str | None:
    if not strings:
        return None
    for s in strings:
        if s.lang is None:
            return s.text
    return strings[0].text


def _extension_hint(properties: tuple[ExchangeProperty, ...]) -> str | None:
    for prop in properties:
        if prop.property_definition_ref == _SPECIALIZATION_HINT_KEY and prop.values:
            return prop.values[0].text
    return None


def _decode_properties(
    properties: tuple[ExchangeProperty, ...],
    defs_by_id: dict[str, str],
) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for prop in properties:
        if prop.property_definition_ref.startswith(_RESERVED_PROPERTY_PREFIX):
            continue
        key = defs_by_id.get(prop.property_definition_ref, prop.property_definition_ref)
        decoded[key] = prop.values[0].text if prop.values else ""
    return decoded


def _find_connection_id(store: ConnectionLookup, source: str, target: str, connection_type: str) -> str | None:
    # Not a plain `get_connection(f"{source}---{target}@@{connection_type}")` lookup: that
    # composite id isn't shaped like an entity id, and the index's short-id fallback
    # resolution (meant for entity/connection ids alone) mis-truncates it into a false
    # match against an unrelated connection type between the same two entities.
    for record in store.find_connections_for(source, direction="outbound", conn_type=connection_type):
        if record.target == target:
            return record.artifact_id
    return None


@dataclass
class _ImportContext:
    store: ConnectionLookup
    identity: ExchangeIdentityStore
    mapper: ExchangeConceptMapper
    writer: ExchangeArtifactWriter
    commit: bool
    id_map: dict[str, str] = field(default_factory=dict)


def _import_element(
    ctx: _ImportContext, element: ExchangeElement, defs_by_id: dict[str, str]
) -> ImportedEntity | UnmappableItem:
    hint = _extension_hint(element.properties)
    try:
        mapping = ctx.mapper.element_to_archimate(element.concept_type, specialization_hint=hint)
    except UnmappableConceptError as exc:
        return UnmappableItem(element.identifier, "element", element.concept_type, str(exc))

    name = _primary_text(element.names) or element.identifier
    notes = _primary_text(element.documentation)
    properties = _decode_properties(element.properties, defs_by_id)

    existing_id = ctx.identity.artifact_id_for(element.identifier)
    if existing_id is None:
        outcome = ctx.writer.create_entity(
            artifact_type=mapping.archimate_type,
            name=name,
            properties=properties,
            notes=notes,
            specialization=mapping.specialization,
            dry_run=not ctx.commit,
        )
        if ctx.commit:
            ctx.identity.record(element.identifier, outcome.artifact_id)
        action: Literal["created", "updated"] = "created"
    else:
        outcome = ctx.writer.update_entity(
            artifact_id=existing_id,
            name=name,
            properties=properties,
            notes=notes,
            specialization=mapping.specialization,
            dry_run=not ctx.commit,
        )
        action = "updated"

    ctx.id_map[element.identifier] = outcome.artifact_id
    warning = "; ".join(w for w in (mapping.warning, *outcome.warnings) if w) or None
    return ImportedEntity(element.identifier, outcome.artifact_id, name, action, warning)


def _import_relationship(
    ctx: _ImportContext, relationship: ExchangeRelationship, defs_by_id: dict[str, str]
) -> ImportedConnection | UnmappableItem:
    hint = _extension_hint(relationship.properties)
    try:
        mapping = ctx.mapper.relationship_to_archimate(relationship.concept_type, specialization_hint=hint)
    except UnmappableConceptError as exc:
        return UnmappableItem(relationship.identifier, "relationship", relationship.concept_type, str(exc))

    source_id = ctx.id_map.get(relationship.source)
    target_id = ctx.id_map.get(relationship.target)
    if source_id is None or target_id is None:
        return UnmappableItem(
            relationship.identifier,
            "relationship",
            relationship.concept_type,
            "source or target element was not imported",
        )

    description = _primary_text(relationship.documentation) or _primary_text(relationship.names)
    connection_type = mapping.connection_type
    specialization = mapping.specialization
    warning = mapping.warning

    existing_id = _find_connection_id(ctx.store, source_id, target_id, connection_type)
    if existing_id is not None:
        return ImportedConnection(relationship.identifier, existing_id, "skipped", warning)
    if connection_type != "archimate-association":
        # A pre-existing association between the same pair is treated as a prior
        # downgrade of this exact relationship (re-import idempotence) rather than
        # re-attempting (and re-reporting) the same fallback every time.
        association_id = _find_connection_id(ctx.store, source_id, target_id, "archimate-association")
        if association_id is not None:
            return ImportedConnection(relationship.identifier, association_id, "skipped", warning)

    try:
        outcome = ctx.writer.add_connection(
            source=source_id,
            target=target_id,
            connection_type=connection_type,
            description=description,
            specialization=specialization,
            src_multiplicity=None,
            tgt_multiplicity=None,
            extra_known_ids=frozenset(ctx.id_map.values()),
            dry_run=not ctx.commit,
        )
    except InvalidRelationshipError as exc:
        if connection_type == "archimate-composition":
            return UnmappableItem(
                relationship.identifier,
                "relationship",
                relationship.concept_type,
                f"composition is never downgraded to another type: {exc}",
            )
        connection_type = "archimate-association"
        specialization = None
        warning = (
            f"'{mapping.connection_type}' not permitted between the resolved entity types; "
            "downgraded to association"
        )
        outcome = ctx.writer.add_connection(
            source=source_id,
            target=target_id,
            connection_type=connection_type,
            description=description,
            specialization=None,
            src_multiplicity=None,
            tgt_multiplicity=None,
            extra_known_ids=frozenset(ctx.id_map.values()),
            dry_run=not ctx.commit,
        )

    combined_warning = "; ".join(w for w in (warning, *outcome.warnings) if w) or None
    return ImportedConnection(relationship.identifier, outcome.artifact_id, "created", combined_warning)


def import_model(
    document: ExchangeModel,
    *,
    store: ConnectionLookup,
    identity: ExchangeIdentityStore,
    mapper: ExchangeConceptMapper,
    writer: ExchangeArtifactWriter,
    commit: bool = False,
) -> ImportReport:
    defs_by_id = {d.identifier: (_primary_text(d.names) or d.identifier) for d in document.property_definitions}
    ctx = _ImportContext(store=store, identity=identity, mapper=mapper, writer=writer, commit=commit)

    entities: list[ImportedEntity] = []
    unmappable: list[UnmappableItem] = []
    for element in document.elements:
        element_result = _import_element(ctx, element, defs_by_id)
        if isinstance(element_result, ImportedEntity):
            entities.append(element_result)
        else:
            unmappable.append(element_result)

    connections: list[ImportedConnection] = []
    for relationship in document.relationships:
        relationship_result = _import_relationship(ctx, relationship, defs_by_id)
        if isinstance(relationship_result, ImportedConnection):
            connections.append(relationship_result)
        else:
            unmappable.append(relationship_result)

    return ImportReport(
        committed=commit,
        entities=tuple(entities),
        connections=tuple(connections),
        unmappable=tuple(unmappable),
    )
