"""C19C v3.1 model-exchange export use case (D10, parent plan §4.5, WU-F3b).

Applies the reverse (ArchiMate 4 -> 3.x) side of the Appendix E.4 migration table (via
``ExchangeConceptMapper``) to a caller-selected scope of entities plus every connection
between them, producing an ``ExchangeModel`` ready for ``ExchangeDocumentWriter``. Never
raises on an individual unmappable/out-of-scope item — every such case is collected into
``ExportReport.unexportable`` with a reason, per the lossy-case policy's "never silent" rule.

Exchange ``identifier`` values must be XML ``xs:ID`` (NCName: no ``@``); this repo's own
artifact ids use ``@`` as the prefix/epoch separator, so every identifier this module emits
is a sanitized derivative of the real artifact id, not the id itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.application.artifact_parsing import parse_entity_content_sections
from src.application.exchange.concept_mapping import ExchangeConceptMapper, UnmappableArchimateTypeError
from src.application.exchange.document import (
    ExchangeElement,
    ExchangeModel,
    ExchangeProperty,
    ExchangePropertyDefinition,
    ExchangeRelationship,
    LangString,
)
from src.application.exchange.read_ports import ConnectionLookup, EntityLookup

_SPECIALIZATION_PROPERTY_ID = "archrepo-specialization"
_SRC_MULTIPLICITY_PROPERTY_ID = "archrepo-src-multiplicity"
_TGT_MULTIPLICITY_PROPERTY_ID = "archrepo-tgt-multiplicity"
_NCNAME_INVALID = re.compile(r"[^A-Za-z0-9_.-]")


def _exchange_identifier(artifact_id: str) -> str:
    return artifact_id.replace("@", "_")


def _property_definition_id(attribute_name: str) -> str:
    return f"prop-{_NCNAME_INVALID.sub('-', attribute_name)}"


@dataclass(frozen=True)
class ExportedEntity:
    artifact_id: str
    exchange_id: str
    concept_type: str


@dataclass(frozen=True)
class ExportedConnection:
    artifact_id: str
    exchange_id: str
    concept_type: str


@dataclass(frozen=True)
class UnexportableItem:
    artifact_id: str
    kind: Literal["element", "relationship"]
    archimate_type: str
    reason: str


@dataclass(frozen=True)
class ExportReport:
    document: ExchangeModel
    entities: tuple[ExportedEntity, ...] = ()
    connections: tuple[ExportedConnection, ...] = ()
    unexportable: tuple[UnexportableItem, ...] = ()


@dataclass
class _PropertyDefinitions:
    _seen: dict[str, ExchangePropertyDefinition]

    def ensure(self, identifier: str, name: str) -> str:
        if identifier not in self._seen:
            self._seen[identifier] = ExchangePropertyDefinition(
                identifier=identifier, data_type="string", names=(LangString(name),)
            )
        return identifier

    def all(self) -> tuple[ExchangePropertyDefinition, ...]:
        return tuple(self._seen.values())


def _decoded_properties(content_text: str, defs: _PropertyDefinitions) -> tuple[ExchangeProperty, ...]:
    raw = parse_entity_content_sections(content_text)["properties"]
    return tuple(
        ExchangeProperty(
            property_definition_ref=defs.ensure(_property_definition_id(key), key),
            values=(LangString(value),),
        )
        for key, value in raw.items()
    )


def _specialization_property(specialization: str, defs: _PropertyDefinitions) -> ExchangeProperty:
    defs.ensure(_SPECIALIZATION_PROPERTY_ID, "ArchiMate 4 specialization")
    return ExchangeProperty(property_definition_ref=_SPECIALIZATION_PROPERTY_ID, values=(LangString(specialization),))


def _multiplicity_property(identifier: str, name: str, value: str, defs: _PropertyDefinitions) -> ExchangeProperty:
    defs.ensure(identifier, name)
    return ExchangeProperty(property_definition_ref=identifier, values=(LangString(value),))


def export_model(
    entity_ids: list[str],
    *,
    entities: EntityLookup,
    connections: ConnectionLookup,
    mapper: ExchangeConceptMapper,
    model_identifier: str = "arch-repo-export",
) -> ExportReport:
    """Export *entity_ids* plus every connection between two exported entities.

    ``entities`` needs only ``get_entity``; ``connections`` needs ``find_connections_for``.
    Separate narrow parameters (rather than one composite store) because the two concerns —
    point lookup vs. graph traversal — are independently fakeable in tests.
    """
    defs = _PropertyDefinitions({})
    id_map: dict[str, str] = {}
    exported_entities: list[ExportedEntity] = []
    elements: list[ExchangeElement] = []
    unexportable: list[UnexportableItem] = []

    for artifact_id in entity_ids:
        entity = entities.get_entity(artifact_id)
        if entity is None:
            unexportable.append(UnexportableItem(artifact_id, "element", "", "entity not found"))
            continue
        try:
            mapping = mapper.element_to_exchange(
                entity.artifact_type, entity.specialization or None, domain_hint=entity.domain
            )
        except UnmappableArchimateTypeError as exc:
            unexportable.append(UnexportableItem(artifact_id, "element", entity.artifact_type, str(exc)))
            continue

        exchange_id = _exchange_identifier(artifact_id)
        id_map[artifact_id] = exchange_id
        sections = parse_entity_content_sections(entity.content_text)
        properties = list(_decoded_properties(entity.content_text, defs))
        if mapping.extension_specialization:
            properties.append(_specialization_property(mapping.extension_specialization, defs))

        elements.append(
            ExchangeElement(
                identifier=exchange_id,
                concept_type=mapping.concept_type,
                names=(LangString(entity.name),),
                documentation=(LangString(sections["summary"]),) if sections["summary"] else (),
                properties=tuple(properties),
            )
        )
        exported_entities.append(ExportedEntity(artifact_id, exchange_id, mapping.concept_type))

    exported_connections: list[ExportedConnection] = []
    relationships: list[ExchangeRelationship] = []
    seen_connection_ids: set[str] = set()

    for artifact_id in entity_ids:
        if artifact_id not in id_map:
            continue
        for conn in connections.find_connections_for(artifact_id, direction="outbound"):
            if conn.artifact_id in seen_connection_ids:
                continue
            seen_connection_ids.add(conn.artifact_id)

            if conn.target not in id_map:
                unexportable.append(
                    UnexportableItem(conn.artifact_id, "relationship", conn.conn_type, "target is out of export scope")
                )
                continue
            try:
                mapping = mapper.relationship_to_exchange(conn.conn_type, conn.specialization or None)
            except UnmappableArchimateTypeError as exc:
                unexportable.append(UnexportableItem(conn.artifact_id, "relationship", conn.conn_type, str(exc)))
                continue

            properties = []
            if mapping.extension_specialization:
                properties.append(_specialization_property(mapping.extension_specialization, defs))
            if conn.src_multiplicity:
                properties.append(
                    _multiplicity_property(
                        _SRC_MULTIPLICITY_PROPERTY_ID, "source multiplicity", conn.src_multiplicity, defs
                    )
                )
            if conn.tgt_multiplicity:
                properties.append(
                    _multiplicity_property(
                        _TGT_MULTIPLICITY_PROPERTY_ID, "target multiplicity", conn.tgt_multiplicity, defs
                    )
                )

            exchange_id = _exchange_identifier(conn.artifact_id)
            documentation = (LangString(conn.content_text.strip()),) if conn.content_text.strip() else ()
            relationships.append(
                ExchangeRelationship(
                    identifier=exchange_id,
                    concept_type=mapping.concept_type,
                    source=id_map[artifact_id],
                    target=id_map[conn.target],
                    documentation=documentation,
                    properties=tuple(properties),
                )
            )
            exported_connections.append(ExportedConnection(conn.artifact_id, exchange_id, mapping.concept_type))

    document = ExchangeModel(
        identifier=model_identifier,
        elements=tuple(elements),
        relationships=tuple(relationships),
        property_definitions=defs.all(),
    )
    return ExportReport(
        document=document,
        entities=tuple(exported_entities),
        connections=tuple(exported_connections),
        unexportable=tuple(unexportable),
    )
