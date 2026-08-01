"""Authoring guidance: when to create a type, what it may connect to, and what to fill in.

The same payload MCP's ``artifact_authoring_guidance`` returns, for REST-only consumers — so this is
a transcription of ``get_type_guidance``, not a second view of it.

The attribute descriptors are the entity surface's — ``attribute_descriptors`` serves the entity
schema route and this one from one function, so one typed input component renders either.

The response is a union of four independent answers, each requested by a different query parameter
and each absent when it was not asked for. Absent, not null: the caller knows what it asked for, and
a null section would say "asked and unavailable", which never happens — an unanswerable request is a
422.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from src.infrastructure.gui.contracts.entities import AttributeDescriptor
from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


class MetadataSchemaBlock(NullsOmitted):
    """The effective metadata schema a (connection type, specialization) pair authors against.

    Connections have no schema endpoint of their own — unlike entities, which fetch theirs from
    ``/api/entity-schemata/{artifact_type}`` — so it rides along here.

    ``quarantined`` is a derived read of the *same* conflicts channel, never a parallel one: true
    means the write boundary refuses this pair, and the flag only explains a refusal the backend
    already guarantees.
    """

    #: The merged JSON Schema document itself. Null when no schema file declares one.
    schema_document: dict[str, Any] | None = Field(default=None, alias="schema")
    properties: list[str]
    required: list[str]
    descriptors: dict[str, AttributeDescriptor]
    conflicts: list[str]
    quarantined: bool

    # Merged onto the inherited config, which is what carries the null-omitting claim.
    model_config = ConfigDict(populate_by_name=True)


class SpecializationNotation(NullsOmitted):
    """How a specialization is drawn, where it says anything about that at all."""

    icon: str | None = None
    color: str | None = None


class SpecializationGuidance(NullsOmitted):
    """One specialization of an entity or connection type, and when to reach for it."""

    slug: str
    name: str
    description: str
    create_when: str
    never_create_when: str
    notation: SpecializationNotation | None = None
    #: Connection specializations only, and only when the backend resolved a repository root —
    #: schemas are per-repo files, so without one there is nothing to merge.
    metadata_schema: MetadataSchemaBlock | None = None


class PermittedConnectionsByPeer(NullsOmitted):
    """Which connection types are legal to each peer type, by direction.

    Three maps rather than one: a symmetric relation belongs to neither direction, and folding it
    into either would tell an author it has a source and a target when it does not.
    """

    outgoing: dict[str, list[str]]
    incoming: dict[str, list[str]]
    symmetric: dict[str, list[str]]


class GuidanceContextLayer(NullsOmitted):
    """One layer of composed ancestry context, from the guidance hierarchy this type sits in."""

    level: str
    node: str
    text: str


class EntityTypeGuidance(NullsOmitted):
    """One entity type: how it is identified, what it counts as, and when to create it.

    ``domain`` is present when the request selected types rather than domains — a domain-filtered
    answer already states the domain once, at the top, and repeating it per row would be noise.
    """

    name: str
    prefix: str
    domain: str | None = None
    classes: list[str]
    create_when: str
    never_create_when: str
    permitted_connections: PermittedConnectionsByPeer
    specializations: list[SpecializationGuidance]
    #: Composed ancestry context, broadest first. Absent where the hierarchy says nothing.
    context: list[GuidanceContextLayer] | None = None


class ConnectionTypeGuidance(NullsOmitted):
    """One connection type, its specializations, and the schema they author against.

    A type appears only when it has something to say — imported guidance, a specialization, or a
    base schema — so the absence of a type here is not a claim that it is illegal.
    """

    name: str
    create_when: str
    never_create_when: str
    specializations: list[SpecializationGuidance]
    metadata_schema: MetadataSchemaBlock | None = None


class PairGuidance(NullsOmitted):
    """Which connection types are legal between one ordered pair of entity types.

    Closed and error-free: an unknown target used to arrive here as a 200 carrying ``error`` and
    ``known_types``, which the route now rejects as a 422 like every other bad input.
    """

    source: str
    target: str
    outgoing: list[str]
    incoming: list[str]
    symmetric: list[str]


class PermittedMappingSource(NullsOmitted):
    """One ontology a diagram-owned entity type may map onto, and how transparently.

    A source names *either* a type or a class, so the other one is absent rather than empty — an
    empty string would read as "a class whose name is nothing".
    """

    ontology: str
    entity_type: str | None = None
    entity_class: str | None = None
    #: Whether the mapping is invisible to the reader — the diagram element *is* the model entity,
    #: rather than standing beside it.
    transparent: bool


class PermittedMappings(NullsOmitted):
    """What a diagram-owned entity type may be linked to in the model."""

    entity_types: list[str]
    entity_classes: list[str]
    sources: list[PermittedMappingSource] | None = None


class OwnEntityTypeGuidance(NullsOmitted):
    """One entity type a diagram kind owns rather than borrows from the model.

    ``min``/``max`` are the cardinality the kind requires on a diagram — a sequence diagram with no
    lifelines is not a sequence diagram.
    """

    entity_type: str
    label: str
    min: int
    max: int | None
    classes: list[str]
    create_when: str
    never_create_when: str
    permitted_mappings: PermittedMappings | None = None
    #: Field name → what the kind does with it: ``required``, ``optional``, or a sentence saying
    #: what it falls back to. Prose because the answer is conditional on the mapping.
    managed_fields: dict[str, str]
    #: The kind's own per-type properties, each a JSON Schema fragment with ``required`` beside it.
    domain_properties: dict[str, Any] | None = None


class BindingTargetSpec(NullsOmitted):
    """What one diagram element may be bound to, and under which correspondence.

    ``target_connection_types``/``target_connection_classes`` narrow a connection binding; an entity
    binding has neither, which is why they are absent rather than empty.
    """

    correspondence_kinds: list[str]
    default_correspondence_kind: str
    target_forms: list[str]
    visual_roles: list[str] | None = None
    target_connection_types: list[str] | None = None
    target_connection_classes: list[str] | None = None


class AllowedBindings(NullsOmitted):
    """Which of a diagram kind's elements may be bound to the model, keyed by element type.

    Two open *maps* with a closed value: the keys are the kind's own element types, which are the
    module's to name, and enumerating them here would make this file change with every module.
    """

    entity: dict[str, BindingTargetSpec]
    connection: dict[str, BindingTargetSpec]


class DiagramTypeGuidance(NullsOmitted):
    """One diagram kind: when to draw it, what it owns, and what it may bind to.

    ``guidance_status`` is ``empty`` when the shipped ontology carries no ``create_when`` text —
    stripped for licence reasons — and ``guidance_hint`` says how to import it. A surface that
    showed blank guidance without saying why would look broken.
    """

    name: str
    when_to_use: str
    when_not_to_use: str
    accepted_domains: list[str] | None = None
    #: A JSON Schema for the kind's ``diagram-entities`` block. The document's own vocabulary, so it
    #: is served as written rather than mirrored here.
    diagram_entities_schema: dict[str, Any] | None = None
    own_entity_types: list[OwnEntityTypeGuidance] | None = None
    puml_notes: list[str] | None = None
    allowed_bindings: AllowedBindings | None = None
    guidance_status: Literal["empty"] | None = None
    guidance_hint: str | None = None


class AuthoringGuidanceResponse(NullsOmitted):
    """Four independent answers, each present only if it was asked for.

    ``entity_types``/``total``/``connection_types`` arrive together and describe the type
    vocabulary; ``domains`` names the filter when the request selected by domain rather than by
    type; ``diagram_type_guidance`` answers ``diagram_type=``; ``pair_guidance`` answers
    ``target=``. A request that names none of them gets the whole type vocabulary.
    """

    entity_types: list[EntityTypeGuidance] | None = None
    total: int | None = None
    #: The domains the request filtered by — present only on a domain-filtered answer, where the
    #: rows omit their own ``domain``.
    domains: list[str] | None = None
    connection_types: list[ConnectionTypeGuidance] | None = None
    diagram_type_guidance: DiagramTypeGuidance | None = None
    pair_guidance: PairGuidance | None = None
    guidance_status: Literal["empty"] | None = None
    guidance_hint: str | None = None
