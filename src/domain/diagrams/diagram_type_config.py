"""Diagram-type configuration dataclasses and builder helpers.

Extracted from ontology_protocol to keep that module within LoC limits.
All public names are re-exported from src.domain.ontology_representation.ontology_protocol for
backward compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec
from src.domain.ontology_representation.ontology_types import (
    ElementClassInfo,
    PermittedMappingSpec,
    RequiredConnection,
    mapping_spec_from_config,
)
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet, permitted_connections_from_config


@dataclass(frozen=True)
class DiagramOwnEntityTypePropertySpec:
    """Domain-specific property for a diagram-only entity type (management fields are auto-added)."""

    name: str
    schema: dict[str, object]
    required: bool = True


@dataclass(frozen=True)
class EditableMetadataField:
    """One editable descriptive-metadata field of a diagram-only entity type (as opposed to a
    structural field). ``control`` names the input widget an editor should render
    (summary/notes/text/boolean/tags)."""

    field: str
    control: str = "text"


@dataclass(frozen=True)
class EditableMetadataSpec:
    """A diagram-only entity type's editable descriptive metadata: ``entity`` fields (on the record
    itself) and ``subparts`` fields (on a named sub-collection, e.g. a classifier's ``attributes``).
    A property of the type — the single source both the PATCH write-op whitelist and every edit
    surface derive from, declared once in the diagram type's config."""

    entity: tuple[EditableMetadataField, ...] = ()
    subparts: Mapping[str, tuple[EditableMetadataField, ...]] = field(default_factory=dict)

    def fields_for(self, subpart: str | None) -> tuple[EditableMetadataField, ...]:
        """Editable fields for the record itself (``subpart is None``) or one of its sub-parts."""
        return self.entity if subpart is None else tuple(self.subparts.get(subpart, ()))

    def field_names(self, subpart: str | None) -> frozenset[str]:
        return frozenset(f.field for f in self.fields_for(subpart))


def _editable_metadata_fields_from_config(raw: object) -> tuple[EditableMetadataField, ...]:
    return tuple(
        EditableMetadataField(field=str(item["field"]), control=str(item.get("control", "text")))
        for item in (raw if isinstance(raw, list) else ())
        if isinstance(item, Mapping) and item.get("field")
    )


def _editable_metadata_from_config(raw: object) -> EditableMetadataSpec:
    if not isinstance(raw, Mapping):
        return EditableMetadataSpec()
    subparts_raw = raw.get("subparts")
    subparts = {
        str(name): _editable_metadata_fields_from_config(fields)
        for name, fields in (subparts_raw.items() if isinstance(subparts_raw, Mapping) else ())
    }
    return EditableMetadataSpec(
        entity=_editable_metadata_fields_from_config(raw.get("entity")),
        subparts=subparts,
    )


@dataclass(frozen=True)
class DiagramOwnEntityTypeUiConfig:
    entity_type: str
    label: str
    plural: str
    min: int = 0
    max: int | None = None
    permitted_mappings: PermittedMappingSpec = field(default_factory=PermittedMappingSpec)
    mapping_required: bool = False
    classes: tuple[str, ...] = ()
    create_when: str = ""
    never_create_when: str = ""
    properties: tuple[DiagramOwnEntityTypePropertySpec, ...] = ()
    permitted_connections: PermittedRelationshipSet = field(default_factory=PermittedRelationshipSet.empty)
    required_connections: tuple[RequiredConnection, ...] = ()
    managed_fields: tuple[tuple[str, str], ...] | None = None
    identity_scope: Literal["diagram", "workspace"] = "diagram"
    id_prefix: str | None = None
    include_in_global_search: bool = False
    editable_metadata: EditableMetadataSpec = field(default_factory=EditableMetadataSpec)


@dataclass(frozen=True)
class DiagramTypeUiConfig:
    label: str
    description: str = ""
    entity_search_filter: bool = True
    diagram_only_types: tuple[DiagramOwnEntityTypeUiConfig, ...] = ()
    type_ui_slots: dict[str, str] = field(default_factory=dict)
    primitive_types: tuple[str, ...] = ()


def diagram_type_ui_config_from_mapping(
    config: Mapping[str, Any],
    *,
    default_label: str,
) -> DiagramTypeUiConfig:
    ui = config.get("ui")
    if not isinstance(ui, Mapping):
        return DiagramTypeUiConfig(label=default_label, entity_search_filter=True)
    return DiagramTypeUiConfig(
        label=str(ui.get("label") or default_label),
        description=str(ui.get("description") or ""),
        entity_search_filter=bool(ui.get("entity_search_filter", True)),
        diagram_only_types=tuple(
            _own_entity_ui_config_from_mapping(entry)
            for entry in ui.get("diagram_only_types", ())
            if isinstance(entry, Mapping)
        ),
        type_ui_slots={str(k): str(v) for k, v in ui.get("type_ui_slots", {}).items()},
        primitive_types=tuple(str(t) for t in ui.get("primitive_types", ())),
    )


def _own_entity_ui_config_from_mapping(config: Mapping[str, Any]) -> DiagramOwnEntityTypeUiConfig:
    mapping_spec = mapping_spec_from_config(config.get("permitted_mappings"))
    raw_props: object = config.get("properties") or {}
    props = tuple(
        DiagramOwnEntityTypePropertySpec(
            name=name,
            schema={k: v for k, v in spec.items() if k != "required"},
            required=bool(spec.get("required", True)),
        )
        for name, spec in (raw_props.items() if isinstance(raw_props, Mapping) else ())
        if isinstance(spec, Mapping)
    )
    raw_conns = config.get("permitted_connections")
    raw_req = config.get("required_connections") or ()
    max_val = config.get("max")
    return DiagramOwnEntityTypeUiConfig(
        entity_type=str(config["entity_type"]),
        label=str(config["label"]),
        plural=str(config.get("plural") or config["label"] + "s"),
        min=int(config.get("min", 0)),
        max=None if max_val is None else int(max_val),
        permitted_mappings=mapping_spec,
        mapping_required=bool(config.get("mapping_required", False)),
        classes=tuple(str(c) for c in config.get("classes", ())),
        create_when=str(config.get("create_when") or ""),
        never_create_when=str(config.get("never_create_when") or ""),
        properties=props,
        permitted_connections=(
            permitted_connections_from_config(raw_conns)
            if isinstance(raw_conns, list)
            else PermittedRelationshipSet.empty()
        ),
        required_connections=tuple(_required_connection_from_mapping(rc) for rc in raw_req if isinstance(rc, Mapping)),
        managed_fields=_parse_managed_fields(config.get("managed_fields")),
        identity_scope=str(config.get("identity_scope") or "diagram"),  # type: ignore[arg-type]
        id_prefix=(str(config["id_prefix"]) if config.get("id_prefix") else None),
        include_in_global_search=bool(config.get("include_in_global_search", False)),
        editable_metadata=_editable_metadata_from_config(config.get("editable_metadata")),
    )


def _parse_managed_fields(raw: object) -> tuple[tuple[str, str], ...] | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    return tuple((str(k), str(v)) for k, v in raw.items())


def _required_connection_from_mapping(config: Mapping[str, Any]) -> RequiredConnection:
    raw_card = config.get("cardinality") or [1, 1]
    card_min = int(raw_card[0]) if raw_card else 1
    card_max: int | None = int(raw_card[1]) if len(raw_card) > 1 and raw_card[1] is not None else None
    return RequiredConnection(
        connection_type=str(config["connection_type"]),
        target=str(config["target"]),
        cardinality_min=card_min,
        cardinality_max=card_max,
    )


@dataclass(frozen=True)
class DiagramTypeWriteGuidance:
    """Authoring guidance for one diagram type, returned by artifact_authoring_guidance(diagram_type=...)."""

    when_to_use: str
    when_not_to_use: str
    accepted_domains: tuple[str, ...] = ()
    diagram_entities_schema: dict[str, object] | None = None
    own_entity_types: tuple[DiagramOwnEntityTypeUiConfig, ...] = ()
    puml_notes: tuple[str, ...] = ()
    allowed_bindings: AllowedBindingsSpec | None = None


def puml_notes_from_config(config: Mapping[str, Any]) -> tuple[str, ...]:
    """The ``guidance.puml_notes:`` list of one diagram type's configuration.

    The authoring *protocol* — which connection types wire what to what, which of them are
    mandatory, what an omission does — is the part of a diagram type an author cannot read off
    the schema, and for every type but ArchiMate it was undocumented: it had to be
    reverse-engineered from an existing `.puml`, i.e. after authoring one. It lives beside
    `when_to_use` because it is guidance, not behaviour, and because a type whose other guidance
    is in configuration should not keep this one piece in code.

    Entries that are not strings are dropped rather than raising: guidance that is malformed is
    still guidance nobody is blocked by.
    """
    guidance = config.get("guidance")
    if not isinstance(guidance, Mapping):
        return ()
    notes = guidance.get("puml_notes")
    if not isinstance(notes, list):
        return ()
    return tuple(str(note) for note in notes if isinstance(note, str))


@dataclass(frozen=True)
class DiagramRendererReferences:
    """Model artifact references discovered by a renderer from diagram-owned data."""

    entity_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()


def element_classes_from_config(config: Mapping[str, Any]) -> dict[str, ElementClassInfo]:
    """The ``element_classes:`` block of one diagram type's configuration.

    Four diagram types — c4, datatype, sequence, activity — each carried a byte-identical private
    copy of this. Reading a *configuration key* is not a per-kind decision: the key, its shape and
    the tolerance for a malformed block all belong to whatever defines the configuration, which is
    this module. Four copies is four places for a schema change to be applied three times.

    A block that is not a mapping yields nothing rather than raising. A diagram type whose
    configuration is malformed here still loads and simply declares no element classes; refusing the
    whole type would take the ontology down for a cosmetic field.
    """
    raw: object = config.get("element_classes") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(name): ElementClassInfo(
            name=str(name),
            description=str((info or {}).get("description") or "") if isinstance(info, Mapping) else "",
        )
        for name, info in raw.items()
    }
