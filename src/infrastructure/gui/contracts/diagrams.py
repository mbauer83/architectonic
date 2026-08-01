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

from src.infrastructure.gui.contracts.connections import ConnectionSummary
from src.infrastructure.gui.contracts.entities import (
    ContextConnection,
    EntityDisplayItemResponse,
    EntitySummary,
)
from src.infrastructure.gui.contracts.viewpoints import ViewpointApplicationResponse
from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ModuleShaped(BaseModel):
    """A payload whose fields belong to a diagram-type module rather than to this surface.

    Open on purpose, and named so the exception is auditable: the alternative is a delivery-layer
    model that has to change whenever a diagram kind adds a field, which would make the ontology's
    extensibility depend on this file.
    """

    model_config = ConfigDict(extra="allow")


class DiagramEntityItem(_ModuleShaped):
    """One entity as it is placed on a diagram: identity plus the kind's own placement data."""

    artifact_id: str
    name: str | None = None
    artifact_type: str | None = None


class DiagramEntityListResponse(_Closed):
    """Entities placed on one diagram."""

    items: list[DiagramEntityItem]


class DiagramConnectionItem(_ModuleShaped):
    """One connection as it is drawn on a diagram."""

    artifact_id: str | None = None
    source: str | None = None
    target: str | None = None
    conn_type: str | None = None


class DiagramConnectionListResponse(_Closed):
    """Connections drawn on one diagram."""

    items: list[DiagramConnectionItem]


class DiagramReference(_Closed):
    """A diagram that draws a given source/target pair."""

    artifact_id: str
    name: str


class DiagramReferenceListResponse(_Closed):
    """Which diagrams draw a given pair — what a rename or removal has to warn about."""

    items: list[DiagramReference]


class DiagramTypeMemberItem(_ModuleShaped):
    """One entity or connection type a diagram kind accepts, with its presentation data."""

    key: str | None = None
    label: str | None = None


class DiagramTypeEntityTypeListResponse(_Closed):
    items: list[DiagramTypeMemberItem]


class DiagramTypeConnectionTypeListResponse(_Closed):
    items: list[DiagramTypeMemberItem]


class DiagramSummary(_Closed):
    """One row of the diagram list."""

    artifact_id: str
    diagram_type: str
    name: str
    version: str
    status: str
    path: str
    is_global: bool
    group: str | None = None
    keywords: list[str] = []
    host_diagram_id: str | None = None
    last_updated: str | None = None
    tlp: str | None = None
    viewpoint: ViewpointApplicationResponse | None = None


class DiagramListResponse(_Closed):
    """A page of diagrams, with the count of the *filtered* population."""

    total: int
    items: list[DiagramSummary]


class DatatypeClassifierInfo(_Closed):
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


class DatatypeTypeListResponse(_Closed):
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


class DatatypeTypeUsage(_Closed):
    """One place a classifier type is referenced as an attribute's type."""

    diagram_id: str
    classifier_local_id: str
    attr_name: str


class DatatypeTypeUsageResponse(_Closed):
    """Everywhere one classifier type is used.

    ``type_id`` is echoed although the caller supplied it in the path: a client that fans out over
    several types and collects the answers needs each one to say which question it answers, and
    correlating by request order is the kind of thing that works until it does not.
    """

    type_id: str
    usages: list[DatatypeTypeUsage]


class MatrixConnTypeConfig(_Closed):
    """One relationship type the matrix draws, and whether it is currently shown."""

    conn_type: str
    active: bool


class MatrixConfigResponse(_Closed):
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


class EntityDisplaySearchResponse(_Closed):
    """A page of entities a user could place on a diagram.

    ``next_cursor`` is an offset the caller passes back verbatim; null means this page is the last.
    The cursor is opaque by contract — the ordering it encodes is the server's to change.
    """

    items: list[EntityDisplayItemResponse]
    next_cursor: str | None


class HopSuggestionGroup(_Closed):
    """Entities one hop further out than the last group, so a picker can offer "and their
    neighbours" without asking the user to think in graph distance.

    ``hop`` starts at 1: hop 0 is what the diagram already holds, and repeating it would invite a
    surface to offer removing an entity as a suggestion to add one.
    """

    hop: int
    items: list[EntityDisplayItemResponse]


class DiagramEntityDiscoveryResponse(_Closed):
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


class DerivedViewEntityResponse(_Closed):
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


class DiagramPreviewResponse(_Closed):
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


class _ModuleShapedRecord(NullsOmitted):
    """A module-extensible payload whose unset optionals are absent rather than null.

    Two claims that have to travel together on the diagram reads. ``extra="allow"`` because a
    diagram-type module contributes top-level keys through ``read_diagram_extras`` and
    ``build_context_extras`` — a matrix's body, a C4 diagram's navigation — and enumerating them here
    would make the ontology's extensibility depend on this file. The null policy because the same
    responses embed :class:`EntitySummary`, which is null-omitting on the entity list and cannot
    have two policies for one schema.
    """

    model_config = ConfigDict(extra="allow")


class DiagramDetailResponse(_ModuleShapedRecord):
    """One diagram, read whole: the record, its source, and what the source declares.

    ``entity_ids_used``/``connection_ids_used`` are present only when the file's frontmatter
    declares them — an older diagram simply does not, and an empty list would claim it draws
    nothing.

    Open at this level, and only this level: ``read_diagram_extras`` is a diagram-type module hook
    returning top-level keys, so what a matrix or a C4 diagram adds arrives beside these fields
    rather than nested under them.
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


class DiagramContextResponse(_ModuleShapedRecord):
    """A diagram and everything an editor needs to work on it, in one read.

    Assembled server-side because an editor that fetched these separately could render a diagram
    against one model generation and its candidate connections against another. ``generation`` and
    ``etag`` are in the body for exactly that reason: they say which snapshot all of it came from.

    ``explicit_connection_pairs`` are the source/target alias pairs the PUML actually draws, which
    is how a stated connection is told from one that merely exists between two placed entities.

    Open at this level for ``build_context_extras``: a C4 diagram contributes its navigation here.
    """

    diagram: DiagramDetailResponse
    entities: list[DiagramContextEntity]
    connections: list[DiagramContextConnection]
    candidate_connections: list[ContextConnection]
    suggested_entities: list[HopSuggestionGroup]
    explicit_connection_pairs: list[tuple[str, str]]
    generation: int
    etag: str
