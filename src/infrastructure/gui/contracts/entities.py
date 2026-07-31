"""Response contracts for the entity surface.

Closed models: no ``extra="allow"``. The open form documented "an object" and promised nothing, so
the only executable statement of what an entity read contains was the frontend's decoder — the
contract on the wrong side of the boundary. Every field a client may rely on is declared here.

Three fields stay open maps, and they are the reason a *named* dynamic set exists rather than a
blanket exception: ``attributes``/``properties`` keys are declared by the entity type's attribute
schema at authoring time, ``extra`` is unmodelled frontmatter the repository round-trips verbatim,
and ``display_blocks`` is rendering data whose shape belongs to the diagram-type module. All three
are repository or module data rather than part of this contract. Anything else that wants an open
map has to justify itself the same way.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntitySummary(NullsOmitted):
    """One row of the entity list: enough to render, filter, link and badge.

    ``conn_in``/``conn_sym``/``conn_out`` are three numbers rather than one: a symmetric relation
    belongs to neither direction, and folding it into either would make a badge disagree with the
    connection list the user then opens. ``host_diagram_id`` is present only for a diagram-owned
    construct, which is how a display surface tells one from a model entity.
    """

    artifact_id: str
    artifact_type: str
    name: str
    version: str
    status: str
    domain: str
    subdomain: str
    path: str
    is_global: bool
    group: str | None = None
    specialization: str | None = None
    host_diagram_id: str | None = None
    conn_in: int | None = None
    conn_sym: int | None = None
    conn_out: int | None = None
    last_updated: str | None = None


class EntityListResponse(NullsOmitted):
    """A page of entities, with the count of the *filtered* population.

    ``total`` is the size of the population the filters select, not of the page — a facet whose
    count came from the page would read zero for every filter not yet scrolled into.
    """

    total: int
    items: list[EntitySummary]


class DocumentReference(NullsOmitted):
    """A document that cites this entity, and the link it cites it through.

    Mirrors ``application.document_links.DocumentEntityReference`` field for field, because that is
    what the handler serialises — this contract is a projection of that output, not an independent
    description of it. An earlier version of this DTO named ``artifact_id`` where the producer emits
    ``document_id`` and omitted ``label``/``href`` altogether; being closed, it then rejected every
    real reference and the detail read answered 500 for any entity a document cites.
    ``test_document_reference_contract.py`` holds the two together.

    ``label`` and ``href`` are the citation itself — the link text and the target as written. They
    ride along because a reference list that cannot show *how* the document refers to the entity
    makes the reader open the document to find out.
    """

    document_id: str
    title: str
    doc_type: str
    path: str
    section: str
    label: str
    href: str


class EntityRecordFields(NullsOmitted):
    """The indexed record, as every entity read returns it.

    Shared by the detail read and the context read so the two cannot describe the same record
    differently — the context read embeds this object rather than restating its fields.
    """

    artifact_id: str
    artifact_type: str
    record_type: str
    name: str
    version: str
    status: str
    domain: str
    subdomain: str
    path: str
    keywords: list[str] = []
    specialization: str | None = None
    specializations: list[str] = []
    content_snippet: str | None = None
    content_text: str | None = None
    display_blocks: dict[str, Any] = {}
    attributes: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    group: str | None = None
    last_updated: str | None = None


class EntityDetailResponse(EntityRecordFields):
    """One entity, with its parsed content sections and its degree.

    ``conn_in``/``conn_sym``/``conn_out`` are three numbers rather than one: a symmetric relation
    belongs to neither direction, and folding it into either would make the counts disagree with the
    connection list the user then opens.
    """

    summary: str | None = None
    properties: dict[str, Any] = {}
    notes: str | None = None
    conn_in: int | None = None
    conn_sym: int | None = None
    conn_out: int | None = None
    is_global: bool | None = None
    referenced_in_documents: list[DocumentReference] = []
    # Set only for a construct a diagram owns — a GSN goal, a swimlane — and the field by which a
    # display surface tells one from a model entity. The client's decoder has always declared it; the
    # server had not, so reading such a construct failed its own response contract. Absent for a model
    # entity rather than null, under this DTO's null-omitting policy.
    host_diagram_id: str | None = None


class EntityConnectionCounts(NullsOmitted):
    """Degree by direction, as the context read reports it."""

    conn_in: int
    conn_out: int
    conn_sym: int


class ContextConnection(NullsOmitted):
    """One connection in an entity's context, with both endpoints already resolved.

    The endpoint names, types, domains and scopes ride along rather than being looked up per row:
    a context view renders every connection, and a client resolving each endpoint itself would issue
    one request per row against data the server already had in hand.
    """

    artifact_id: str
    source: str
    target: str
    conn_type: str
    version: str
    status: str
    path: str
    content_text: str
    associated_entities: list[str]
    src_multiplicity: str
    tgt_multiplicity: str
    specialization: str
    source_name: str
    target_name: str
    source_artifact_type: str
    target_artifact_type: str
    source_domain: str
    target_domain: str
    source_scope: str
    target_scope: str
    # Which end of this connection the entity being read is *not*, and which bucket it fell into.
    # Carried rather than derived, because a symmetric relation has no source-or-target answer and a
    # client comparing ids would have to reinvent that rule per view.
    other_entity_id: str | None = None
    direction: str | None = None


class EntityContextResponse(NullsOmitted):
    """One entity together with its connections, and the model generation they were read at.

    ``connections`` is grouped by direction rather than being one list, because a symmetric relation
    belongs to neither and a flat list would have to invent a direction for it.

    ``etag``/``generation`` are part of the body, not only the header: a client that holds a
    neighbourhood and a detail read needs to know they came from the same generation before drawing
    them as one picture.
    """

    entity: EntityDetailResponse
    connections: dict[str, list[ContextConnection]]
    counts: EntityConnectionCounts
    etag: str | None = None
    generation: int | None = None


class EntityDisplayItemResponse(_Closed):
    """How one entity is drawn, resolved from the ontology.

    Served rather than derived client-side so a diagram and a picker cannot disagree about what the
    same entity looks like. ``diagram_internal`` marks a diagram-owned construct — a swimlane, a
    lifeline — which is pickable in a diagram context but must never outrank or be confused with a
    model entity, so every display surface can partition on it.
    """

    artifact_id: str
    name: str
    artifact_type: str
    domain: str
    subdomain: str
    status: str
    display_alias: str | None = None
    element_type: str
    element_label: str
    diagram_internal: bool


class DerivedNeighbor(_Closed):
    """One neighbour a derivation inferred, with the witness a client needs to trust it.

    ``via_connection_ids`` and ``path`` are the witness: a derived edge that cannot be traced back
    to the stated connections behind it is an assertion the user has no way to check.
    """

    entity_id: str
    type: str
    certainty: str
    hops: int
    via_connection_ids: list[str]
    path: str


class DirectNeighborhood(_Closed):
    """Neighbours reached over stated connections, keyed by hop distance."""

    traversal: Literal["direct"] = "direct"
    hops: dict[str, list[str]]


class DerivedNeighborhood(_Closed):
    """Neighbours reached over derived relationships, each with its witness."""

    traversal: Literal["derived"] = "derived"
    neighbors: list[DerivedNeighbor]


#: A traversal-discriminated union. The two arms are genuinely different answers — a hop map against
#: a witnessed relationship list — and the direct arm previously carried no discriminator at all, so
#: a client could not tell which it had received. ``traversal`` is an alternate execution
#: specification, which the addressing rule leaves in the query; what it must not do is leave the
#: *response* untagged.
EntityNeighborhoodResponse = DirectNeighborhood | DerivedNeighborhood


class EntitySchemaResponse(_Closed):
    """The effective attribute schema for a type, merged with its applied specializations.

    The same schema the verifier validates against, so an authoring form and verification cannot
    drift. ``quarantined`` is a derived read of the *same* conflict channel, not a parallel one: a
    non-empty conflict set means the write boundary will refuse a create or edit for this pair, and
    the flag only explains a refusal the backend already guarantees.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_type: str
    specialization: str
    # Aliased because ``BaseModel.schema`` is taken; FastAPI serializes by alias, so the wire name
    # is ``schema`` and only this declaration knows the difference.
    attribute_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    properties: list[str]
    required: list[str]
    descriptors: dict[str, Any]
    conflicts: list[str]
    quarantined: bool
