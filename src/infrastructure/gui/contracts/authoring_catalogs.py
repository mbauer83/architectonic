"""Response contracts for the authoring catalogs: how relations are drawn, what a document type expects.

These describe the *vocabulary* a client authors against rather than anything authored. Their maps are
keyed by ontology and repository vocabulary — connection type names, document type names — so the keys
stay open and the values are closed: enumerating the keys here would put a module's vocabulary in a
second place, and a term added to a module and not mirrored would fail its own response.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelationNotation(_Closed):
    """How one relationship type is drawn: the line, and the marker at each end.

    Structural rather than named after the relationship — "hollow triangle at the target", not
    "realization" — so a renderer can honour it without knowing this ontology's vocabulary. That is the
    reason these are three plain strings and not an enum: the values come from the ontology
    representation layer, and a delivery-layer enum would have to be extended in lockstep with it.
    """

    line: str
    source: str
    target: str


class RelationNotationsResponse(_Closed):
    """Every known relationship's notation, keyed by connection type.

    Served whole on purpose: a graph surface styles hundreds of edges spanning whatever relationship
    types it meets, and a request per type would be a request per edge in the worst case.
    """

    notations: dict[str, RelationNotation]


class DocumentFrontmatterField(NullsOmitted):
    """One type-specific frontmatter field a document of this type may carry.

    ``array_items_type`` is *absent* for a non-collection field rather than null: the element type of a
    scalar does not exist, and this response omits unset optionals throughout — a single null policy per
    response, because one shared schema cannot honestly claim two.
    """

    name: str
    field_type: str
    array_items_type: str | None = None
    required: bool


class DocumentSectionSpec(NullsOmitted):
    """One section a document of this type carries, and what it should link to.

    Mirrors ``application.artifact_document_schema.SectionSpec.to_dict``, which omits a field it has no
    value for rather than sending an empty one — so the three optionals are *absent*, not null. A
    section with no suggested connections and one whose suggestions are an empty list would otherwise
    look the same, and only the first is a thing the schema can express.
    """

    name: str
    #: Boilerplate the create form pre-fills this section with.
    template: str | None = None
    required_entity_type_connections: list[str] | None = None
    suggested_entity_type_connections: list[str] | None = None


class DocumentTypeResponse(NullsOmitted):
    """What one document type expects: its identity, where it lives, and the sections it requires.

    The connection lists name *entity types* a document of this type should or must link to — the
    schema's own vocabulary, carried through rather than interpreted here.
    """

    doc_type: str
    #: The prefix its artifact ids carry; defaults to the upper-cased type when the schema omits it.
    abbreviation: str
    name: str
    #: Where documents of this type are filed, relative to the repository's document root.
    subdirectory: str
    #: Section *names* that must be present — the flat list, for a caller that only checks presence.
    required_sections: list[str]
    #: The same sections with their authoring detail. `SectionSpec` is a closed four-field shape, which
    #: is why this can be a DTO rather than pass-through YAML.
    sections: list[DocumentSectionSpec]
    extra_frontmatter_fields: list[DocumentFrontmatterField]
    required_entity_type_connections: list[str]
    suggested_entity_type_connections: list[str]


class DocumentTypeListResponse(NullsOmitted):
    """Every document type this repository declares, in type order.

    An envelope rather than a bare array, like every other collection on this surface — and ordered, so
    two reads of an unchanged repository agree rather than presenting whatever order the mapping held.
    """

    document_types: list[DocumentTypeResponse]


class GroupEntryResponse(NullsOmitted):
    """One group within one axis, with its whole-catalog member count.

    Every field is required. The domain's ``GroupEntry`` gives each a default and ``_entry_dict`` emits
    all ten keys, so an absent one never reaches a client — the decoder that declared eight of them
    optional was describing a response the route does not send, and every reader carried a fallback for
    it.
    """

    #: Directory name, and the locator tools pass around.
    slug: str
    #: Stable opaque id (``GRP@…``); survives a rename or a move between tiers.
    id: str
    name: str
    description: str
    order: int
    archived: bool
    #: Model-project axis only: the group the GUI selects first.
    default: bool
    #: Model-project axis only: an ontology-framework restriction, empty when unrestricted.
    meta_ontology: str
    type_filter: list[str]
    #: Members across the whole catalogue, not the currently loaded page — a badge computed from a
    #: group-filtered list reads zero for every group that is not the active one.
    member_count: int


class GroupListResponse(NullsOmitted):
    """The groups on each axis, filtered to one axis when the caller asked for one.

    An axis is **absent** rather than empty when it was filtered out: an empty list means "this axis has
    no groups", and the two must not read the same. The keys are hyphenated on the wire because that is
    what the axis is called; the field names cannot be, hence the aliases.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=(), populate_by_name=True)

    model_projects: list[GroupEntryResponse] | None = Field(default=None, alias="model-projects")
    diagram_collections: list[GroupEntryResponse] | None = Field(
        default=None, alias="diagram-collections"
    )
    document_collections: list[GroupEntryResponse] | None = Field(
        default=None, alias="document-collections"
    )
    analysis_collections: list[GroupEntryResponse] | None = Field(
        default=None, alias="analysis-collections"
    )


class OntologyClassificationResponse(_Closed):
    """What one entity type may connect to, grouped by direction.

    Each map is keyed by the *other* entity type and lists the relationship types available in that
    direction — open maps, because the keys are the ontology's own vocabulary. A symmetric relationship
    appears under ``symmetric`` only, never in both directions, so a caller offering choices does not
    show the same pair twice.
    """

    source_type: str
    outgoing: dict[str, list[str]]
    incoming: dict[str, list[str]]
    symmetric: dict[str, list[str]]


class OntologyPairResponse(_Closed):
    """The relationship types permitted between one ordered pair of entity types.

    Its own route rather than a variant of the classification: the two answer different questions and
    share nothing but the word "ontology". They used to be one address returning whichever shape the
    presence of ``target_type`` selected, which no single schema could describe honestly — and the client
    had already split them into two calls with two decoders, so the URL was the only thing pretending
    they were one operation.
    """

    source_type: str
    target_type: str
    connection_types: list[str]
    #: The subset of ``connection_types`` that are symmetric, so a caller need not ask per type.
    symmetric: list[str]
    #: Each permitted type's relationship kind, or null where the ontology assigns none.
    relationship_kind_map: dict[str, str | None]
