"""Response contracts for the diagram surface.

The list-shaped reads answer an object with ``items`` rather than a bare array. A top-level array
has nowhere to put a total or a cursor, so adding either later would be a second breaking change —
and an array also cannot be a named component in the generated document, which is what the
frontend's type generation keys off.

Diagram *content* stays open where it belongs to a diagram-type module: a datatype classifier's
attributes, an activity step's shape, an entity's display block. Those are the module's vocabulary,
not this contract's, and closing them here would put the delivery layer in the business of every
diagram kind. Everything the surface itself decides is declared.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.infrastructure.rest.contracts.connections import ConnectionSummary
from src.infrastructure.rest.contracts.entities import (
    ContextConnection,
    EntityDisplayItemResponse,
    EntitySummary,
)
from src.infrastructure.rest.contracts.viewpoints import ViewpointApplicationResponse
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed


class _ModuleShaped(BaseModel):
    """A payload whose fields belong to a diagram-type module rather than to this surface.

    Open on purpose, and named so the exception is auditable: the alternative is a delivery-layer
    model that has to change whenever a diagram kind adds a field, which would make the ontology's
    extensibility depend on this file.
    """

    model_config = ConfigDict(extra="allow")


class DiagramReference(Closed):
    """A diagram that draws a given source/target pair."""

    artifact_id: str
    name: str


class DiagramReferenceListResponse(Closed):
    """Which diagrams draw a given pair — what a rename or removal has to warn about."""

    items: list[DiagramReference]


class DiagramTypeMemberItem(_ModuleShaped):
    """One entity or connection type a diagram kind accepts, with its presentation data."""

    key: str | None = None
    label: str | None = None


class DiagramTypeEntityTypeListResponse(Closed):
    items: list[DiagramTypeMemberItem]


class DiagramTypeConnectionTypeListResponse(Closed):
    items: list[DiagramTypeMemberItem]


class DiagramSummary(Closed):
    """One row of the diagram list.

    Four fields left with this release — ``keywords``, ``host_diagram_id``, ``tlp`` and
    ``viewpoint``. ``diagram_to_summary`` never filled any of them, so every row carried an empty
    list and three nulls, and the client stripped all four on decode. A field the producer does not
    fill is not a smaller promise than a wrong one; the pinned viewpoint is reported by the diagram
    read, which does resolve it.
    """

    artifact_id: str
    diagram_type: str
    name: str
    version: str
    status: str
    path: str
    is_global: bool
    group: str | None = None
    last_updated: str | None = None


class DiagramListResponse(Closed):
    """A page of diagrams, with the count of the *filtered* population."""

    total: int
    items: list[DiagramSummary]


class DatatypeClassifierInfo(Closed):
    """One classifier a datatype diagram declares, as the picker needs it.

    ``host_diagram_id`` is the diagram that owns it — a classifier is a diagram-local construct, so
    it has no file of its own and its full identifier is composite (see ``_diagram_entity_extraction``).
    Empty for a workspace-scoped type, which is the difference ``scope`` names.
    """

    type_id: str
    label: str
    kind: str
    scope: str
    host_diagram_id: str


class DatatypeTypeListResponse(Closed):
    """A page of datatype classifier types, with the primitives they may be built from.

    ``generation`` is the index generation the page was read at: a picker holding a page and then
    resolving one of its entries needs to know the two came from the same model, and a stale page that
    silently resolves against a newer index is how a deleted classifier gets offered.

    ``next_cursor`` is null on the last page, following the house pagination convention — present and
    null rather than absent, so a client can tell "no more" from "this server does not paginate".
    """

    generation: int
    primitives: list[str]
    classifiers: list[DatatypeClassifierInfo]
    next_cursor: str | None


class DatatypeTypeUsage(Closed):
    """One place a classifier type is referenced as an attribute's type."""

    diagram_id: str
    classifier_local_id: str
    attr_name: str


class DatatypeTypeUsageResponse(Closed):
    """Everywhere one classifier type is used.

    ``type_id`` is echoed although the caller supplied it in the path: a client that fans out over
    several types and collects the answers needs each one to say which question it answers, and
    correlating by request order is the kind of thing that works until it does not.
    """

    type_id: str
    usages: list[DatatypeTypeUsage]


class MatrixConnTypeConfig(Closed):
    """One relationship type the matrix draws, and whether it is currently shown."""

    conn_type: str
    active: bool


class MatrixPreviewResponse(Closed):
    """A matrix write's dry run: the rendered body it would store, and nothing else.

    The route declared ``WriteResultResponse`` — the six-key mutation envelope — while returning
    ``{"markdown": …}``, so FastAPI's response validation raised on every single call and the
    preview answered 500 with a body that deliberately carries no diagnostic. Nothing noticed
    because a preview is a write-shaped operation, and ``NEVER_REQUESTED_OPERATIONS`` recorded
    ``matrices_preview_matrix`` as never once having answered 2xx: the Preview button on both matrix
    views has never worked through the running server.

    A dry run is not a mutation and does not share its envelope. There is no ``wrote``, no ``path``
    and no ``artifact_id``, because nothing was written and nothing has an address yet.
    """

    #: The matrix body the write would store, with entity ids already linkified.
    markdown: str


class MatrixConfigResponse(Closed):
    """A matrix diagram's authored configuration, parsed out of its PUML frontmatter.

    ``from_entity_ids`` and ``to_entity_ids`` are **present and null** for a square matrix rather than
    absent: null says "no separate axis was authored, so both axes are ``entity_ids``", which is a
    different statement from a field that was never part of the response. The producer emits the keys
    unconditionally, so the contract does too.
    """

    artifact_id: str
    name: str
    status: str
    version: str
    keywords: list[str]
    #: The population when both axes are the same — the square case.
    entity_ids: list[str]
    #: The row axis of an asymmetric matrix; null when the matrix is square.
    from_entity_ids: list[str] | None
    #: The column axis of an asymmetric matrix; null when the matrix is square.
    to_entity_ids: list[str] | None
    conn_type_configs: list[MatrixConnTypeConfig]
    #: Whether the cells combine every active relationship type into one mark.
    combined: bool
    #: The diagram's authored PUML body, which the matrix owns rather than deriving.
    matrix_body: str


class EntityDisplaySearchResponse(Closed):
    """A page of entities a user could place on a diagram.

    ``next_cursor`` is an offset the caller passes back verbatim; null means this page is the last.
    The cursor is opaque by contract — the ordering it encodes is the server's to change.
    """

    items: list[EntityDisplayItemResponse]
    next_cursor: str | None


class HopSuggestionGroup(Closed):
    """Entities one hop further out than the last group, so a picker can offer "and their
    neighbours" without asking the user to think in graph distance.

    ``hop`` starts at 1: hop 0 is what the diagram already holds, and repeating it would invite a
    surface to offer removing an entity as a suggestion to add one.
    """

    hop: int
    items: list[EntityDisplayItemResponse]


class DiagramEntityDiscoveryResponse(Closed):
    """Three ways to find the next thing to put on a diagram, answered together.

    A search over the whole model, the connections that would appear if the entities already
    selected were placed, and what lies one, two or three hops out. One request rather than three
    because the panel shows all three at once, and three would race.
    """

    search_results: list[EntityDisplayItemResponse]
    #: Connections between the entities already selected — what the diagram would gain, not what it
    #: has. Excluded from ``search_results`` by construction: an entity already placed is not a
    #: candidate to place.
    candidate_connections: list[ContextConnection]
    suggested_entities: list[HopSuggestionGroup]


class DerivedViewEntityResponse(Closed):
    """One entity a model-backed diagram derived rather than the author placing it.

    ``item_type`` and ``role`` are the diagram-type module's own vocabulary — generic code forwards
    them and never interprets them. ``role`` is load-bearing all the same: the scope root arrives as
    ``scope`` and cannot be excluded, so a checklist offering to remove it offers something the
    engine will not do.
    """

    id: str
    name: str
    item_type: str
    role: str
    excluded: bool


class DiagramPreviewResponse(Closed):
    """What a diagram write would produce, without writing it.

    ``image`` is null when rendering failed and ``warnings`` says why — a preview that cannot render
    is still a successful answer about the write. ``derived_entities`` is null when the diagram type
    derives nothing, which is not the same as deriving nothing *this time*: an empty list means the
    projection ran and found no candidates, and the two read differently to a user.
    """

    puml: str
    image: str | None
    warnings: list[str]
    derived_entities: list[DerivedViewEntityResponse] | None


class DiagramDetailResponse(NullsOmitted):
    """One diagram, read whole: the record, its source, and what the source declares.

    ``entity_ids_used``/``connection_ids_used`` are present only when the file's frontmatter
    declares them — an older diagram simply does not, and an empty list would claim it draws
    nothing.

    ``type_extras`` is where a diagram-type module's own additions arrive. They used to be merged
    into this envelope, which made the whole response an open object promising nothing — a client
    reading the schema was told a diagram read returns "these fields, and possibly anything". One
    declared field carries the module's territory instead, and the envelope closes.
    """

    artifact_id: str
    artifact_type: str
    record_type: Literal["diagram"]
    name: str
    diagram_type: str
    version: str
    status: str
    path: str
    is_global: bool
    group: str | None = None
    last_updated: str | None = None
    content_snippet: str
    puml_source: str
    #: The rendered image beside the source file, absent when nothing has been rendered yet.
    rendered_filename: str | None = None
    entity_ids_used: list[str] | None = None
    connection_ids_used: list[str] | None = None
    #: The diagram-kind's own placement data, keyed by entity id. Absent when the diagram places
    #: nothing of its own — a hand-drawn ArchiMate view, say.
    diagram_entities: dict[str, Any] | None = None
    #: Frontmatter this surface does not model, returned as written.
    extra: dict[str, Any] | None = None
    viewpoint: ViewpointApplicationResponse | None = None
    #: This diagram kind's own additions — a matrix's rendered body, and whatever a future kind
    #: contributes. Absent for a kind that adds nothing.
    type_extras: dict[str, Any] | None = None


class DiagramContextEntity(EntitySummary):
    """One entity as this diagram places it: the list row, plus the alias it is drawn under.

    ``display_alias`` is here and not on :class:`EntitySummary` because only a diagram read resolves
    it — the entity list has no diagram to draw the entity on, and a field the list route never
    fills would read as "this entity has no alias".
    """

    display_alias: str


class DiagramContextConnection(ConnectionSummary, NullsOmitted):
    """One connection as this diagram draws it: the record, plus how it is rendered here.

    The aliases and ``edge_key`` are the PlantUML identity of the edge in *this* file, which is what
    an overlay needs to find the drawn line for a connection. ``edge_label_override`` is the label
    the author set for that edge and belongs to the diagram, not to the connection — the same
    connection drawn on two diagrams can carry two labels.
    """

    source_alias: str
    target_alias: str
    edge_key: str
    edge_label_override: str | None = None


class DiagramEntityListResponse(NullsOmitted):
    """Entities placed on one diagram.

    The rows are :class:`DiagramContextEntity` because they are *the same rows* — the list route and
    the context read both return what ``diagram_entities_and_puml`` produced, and the connection pair
    below does the same for ``diagram_context_payload``'s ``connections``. They used to be declared
    as a pair of open three-field placeholders, which is how one producer came to have two contracts:
    the context read declared the real shape and omitted its unset optionals, while these two
    published a shape nothing produced and sent `"last_updated": null` on the wire. The client
    decodes both with the context read's schema, so the entity list threw in the decoder before a
    row was drawn — the FMEA defect's exact shape, one release later, on a route no browser spec
    happens to read.
    """

    items: list[DiagramContextEntity]


class DiagramConnectionListResponse(NullsOmitted):
    """Connections drawn on one diagram — literally ``diagram_context_payload``'s ``connections``."""

    items: list[DiagramContextConnection]


class DiagramContextResponse(NullsOmitted):
    """A diagram and everything an editor needs to work on it, in one read.

    Assembled server-side because an editor that fetched these separately could render a diagram
    against one model generation and its candidate connections against another. ``generation`` and
    ``etag`` are in the body for exactly that reason: they say which snapshot all of it came from.

    ``explicit_connection_pairs`` are the source/target alias pairs the PUML actually draws, which
    is how a stated connection is told from one that merely exists between two placed entities.
    """

    diagram: DiagramDetailResponse
    entities: list[DiagramContextEntity]
    connections: list[DiagramContextConnection]
    candidate_connections: list[ContextConnection]
    suggested_entities: list[HopSuggestionGroup]
    explicit_connection_pairs: list[tuple[str, str]]
    generation: int
    etag: str
    #: This diagram kind's own additions — a C4 diagram's navigation, and whatever a future kind
    #: contributes. Absent for a kind that adds nothing.
    type_extras: dict[str, Any] | None = None
