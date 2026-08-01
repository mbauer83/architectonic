"""Response contracts for the diagram-type catalogue: the list, and one type's authoring UI config.

Derived by calling the producer, which is how the defect below was found. ``read_diagram_kind_ui_config``
serialised its config with ``dataclasses.asdict``, and ``PermittedRelationshipSet``'s only field is
private — so the wire carried ``permitted_connections: {"_rules": [...]}``. A private attribute name had
become part of an HTTP contract, and a rename inside the domain would have broken every consumer.
``PermittedRelationshipSet.rules()`` is the public reading, and these DTOs use it.

Every level here is closed. The diagram-type modules own *which* types exist and what each declares,
but the vocabulary a declaration is written in is this ontology's and is fixed — so there is nothing
free to leave open, and the alternative (an open map per module) would have published each module's
authoring surface as "an object".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, RootModel

from src.infrastructure.rest.contracts.wire_shape import Closed


class DiagramTypeSummary(Closed):
    """One diagram type a user may create, as a picker needs it.

    Store-projected types are absent: an assurance diagram is derived from an analysis rather than
    authored, so offering it here would offer a "create" that has no meaning.
    """

    key: str
    label: str
    description: str


class MappingSourceSpecResponse(Closed):
    """One ontology source a diagram-own type may be mapped onto.

    ``transparent`` marks a source that maps through without appearing as a choice of its own.
    """

    ontology: str
    entity_type: str | None
    entity_class: str | None
    transparent: bool


class PermittedMappingSpecResponse(Closed):
    """What a diagram-own construct may be mapped to in the model.

    Types and classes are separate because a class is a set of types: a construct permitted for a class
    accepts anything in it, and flattening the two would freeze today's membership into the payload.
    """

    entity_types: list[str]
    entity_classes: list[str]
    sources: list[MappingSourceSpecResponse]


class PermittedRelationshipResponse(Closed):
    """One (source, target, connection) triple a diagram type permits."""

    source_type: str
    target_type: str
    connection_type: str


class RequiredConnectionResponse(Closed):
    """A connection a construct must have, with how many. ``cardinality_max`` null means unbounded."""

    connection_type: str
    target: str
    cardinality_min: int
    cardinality_max: int | None


class DiagramOwnPropertySpecResponse(Closed):
    """One property a diagram-own construct carries.

    ``schema`` is a JSON Schema fragment: its keywords are that specification's, not this surface's —
    the same reason the entity schema route does not mirror them either.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    # Aliased because ``BaseModel.schema`` is taken; FastAPI serialises by alias, so the wire name is
    # ``schema`` and only this declaration knows the difference. Same seam as ``EntitySchemaResponse``.
    property_schema: dict[str, Any] = Field(alias="schema")
    required: bool


class EditableMetadataFieldResponse(Closed):
    """One editable field, and the control an editor should render for it."""

    field: str
    control: str


class EditableMetadataSpecResponse(Closed):
    """Which metadata an editor may change, on the construct and on its subparts.

    ``subparts`` is keyed by subpart name — an open map with a closed value, because which subparts a
    construct has is the module's business and the field list is not.
    """

    entity: list[EditableMetadataFieldResponse]
    subparts: dict[str, list[EditableMetadataFieldResponse]]


class DiagramOwnEntityTypeResponse(Closed):
    """One construct a diagram type owns rather than borrowing from the model.

    ``identity_scope`` decides whether the construct's id is unique to its diagram or to the whole
    workspace — a GSN goal is the diagram's, a datatype classifier is the workspace's — and it is the
    field that decides whether editing one diagram can affect another.

    ``create_when``/``never_create_when`` are guard expressions the authoring surface evaluates;
    ``managed_fields`` is null where nothing is managed, as against an empty list meaning "managed,
    nothing yet".
    """

    entity_type: str
    label: str
    plural: str
    min: int
    max: int | None
    permitted_mappings: PermittedMappingSpecResponse
    mapping_required: bool
    classes: list[str]
    create_when: str
    never_create_when: str
    properties: list[DiagramOwnPropertySpecResponse]
    permitted_connections: list[PermittedRelationshipResponse]
    required_connections: list[RequiredConnectionResponse]
    managed_fields: list[list[str]] | None
    editable_metadata: EditableMetadataSpecResponse
    identity_scope: Literal["diagram", "workspace"]
    id_prefix: str | None
    include_in_global_search: bool


class DiagramTypeUiConfigResponse(Closed):
    """How one diagram type wants its authoring surface built.

    ``type_ui_slots`` maps a construct type to the editor component that should render it, and
    ``primitive_types`` is the built-in type vocabulary a datatype diagram offers — both keyed or listed
    by the module, both closed in shape.
    """

    label: str
    description: str
    entity_search_filter: bool
    diagram_only_types: list[DiagramOwnEntityTypeResponse]
    type_ui_slots: dict[str, str]
    primitive_types: list[str]


class DiagramTypeListResponse(RootModel[list[DiagramTypeSummary]]):
    """The creatable diagram types, as a bare array on the wire.

    A ``RootModel`` rather than ``list[DiagramTypeSummary]`` on the route: the latter publishes an
    inline array schema, which a generated client cannot refer to by name and which the
    response-contract fitness function refuses for that reason. The payload is byte-identical either
    way — this names it.
    """

    root: list[DiagramTypeSummary]
