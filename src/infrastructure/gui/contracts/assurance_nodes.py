"""Response contracts for the assurance node surface: the collection, the detail read, its relations.

Every one of these is a projection of a record the store now hands back in one shape whatever backend
holds it (``assurance/_node_records``, ``assurance/_edge_records``). That was the precondition, not a
detail: a node read embeds a node, its edges and its architecture references, and a contract closed
against one backend's idea of any of the three answered 500 on another.

Its own module rather than more of ``assurance_signals``, which is a different surface — security feeds
anchored to architecture artifacts — and is over the file-length limit besides.

Every count here is taken after exposure filtering, and every degree over the filtered edge set. A
degree counted before the filter would publish the existence of an above-ceiling neighbour through a
number nobody thinks of as content, which is why ``assurance_node_degrees`` runs inside the boundary.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from src.infrastructure.gui.contracts.assurance_analyses import AssuranceAnalysisSummary
from src.infrastructure.gui.contracts.verification import AssuranceVerificationFinding


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssuranceNodeRecord(_Closed):
    """One assurance node, as every backend now hands it back.

    Was open, on the reading that its ``attributes_json`` needed a decision first. It did not: the
    store keeps that column as ``TEXT`` and passes it through unparsed, so the wire carries a JSON
    *string* and the client parses it a second time (``AssuranceGrcWizard.helpers.ts``). A string is a
    ``str``. What actually blocked closing this was that the record had no single shape — nineteen
    columns from SQLCipher, seventeen from the file stores, seventeen plus collection metadata from
    PocketBase — and it is projected at the store boundary now
    (``assurance/_node_records.NODE_RECORD_FIELDS``).

    The nullable fields are the discriminated ones: a hazard has no ``uca_type``, a failure mode no
    ``concern_class``, and a legacy-invalid node no ``analysis_id`` at all — which is the state the
    provenance repair surface exists to fix, so it has to be representable rather than defaulted.
    """

    node_id: str
    node_type: str
    name: str
    status: str
    tlp: str
    concern_class: str | None
    disposition: str | None
    uca_type: str | None
    failure_type: str | None
    mode: str | None
    binding_status: str | None
    node_role: str | None
    analysis_id: str | None
    # The store's own column, passed through unparsed. Not `dict[str, Any]`: parsing it here would be
    # a wire break, and declaring it as an object while sending a string would be a false schema.
    attributes_json: str
    content_text: str
    created_at: str
    updated_at: str


class AssuranceNodeWithDegrees(AssuranceNodeRecord):
    """A node with how many visible edges reach it, in each direction.

    Both counts are always present, including on an isolated node: zero and "not counted" are
    different facts, and omitting the key would make a reader guess which one they had
    (``assurance_node_degrees.with_degrees``).
    """

    conn_in: int
    conn_out: int


class AssuranceNodeListResponse(_Closed):
    """The nodes this reader may see, with their degrees over the edges this reader may see."""

    nodes: list[AssuranceNodeWithDegrees]
    count: int
    visibility_limited: bool


class AssuranceEdgeRecord(_Closed):
    """One edge, as every backend hands it back. ``attributes_json`` is a JSON string, as on a node."""

    edge_id: str
    source_id: str
    target_id: str
    conn_type: str
    attributes_json: str
    created_at: str


class AssuranceEnrichedEdge(AssuranceEdgeRecord):
    """An edge with its endpoints named, so a row renders without a request per endpoint.

    An edge appears only when *both* endpoints are visible to the reader — an edge to a withheld node
    would disclose that node's existence through the shape of the graph
    (``assurance_edge_enrichment.enrich_edges``).
    """

    source_name: str
    source_type: str
    target_name: str
    target_type: str


class AssuranceEdgeListResponse(_Closed):
    """The visible edges, enriched. ``count`` is the length of the list after filtering."""

    edges: list[AssuranceEnrichedEdge]
    count: int
    visibility_limited: bool


class AssuranceArchRefRecord(_Closed):
    """One reference from an assurance node out to an architecture artifact.

    ``resolved_at`` is null until the reference has been checked against the repository — the state the
    binding surface exists to change, and one PocketBase reported as an empty string until the record
    was projected.
    """

    assurance_node_id: str
    arch_artifact_id: str
    ref_type: str
    resolved_at: str | None


class AssuranceNodeDetailResponse(_Closed):
    """One node with its neighbourhood and its two analysis relations.

    ``authored_by`` and ``participates_in`` are separate because they answer different questions —
    *who made this* and *who draws on it* — and a borrowed node has to look borrowed. ``authored_by``
    is null both when the node names no analysis and when it names one above the reader's ceiling: the
    two are deliberately indistinguishable, exactly as they are on a direct read of that analysis.
    ``participates_in`` never lists the author, which would report the node as borrowed from itself.
    """

    node: AssuranceNodeRecord
    outgoing_edges: list[AssuranceEnrichedEdge]
    incoming_edges: list[AssuranceEnrichedEdge]
    arch_refs: list[AssuranceArchRefRecord]
    authored_by: AssuranceAnalysisSummary | None
    participates_in: list[AssuranceAnalysisSummary]
    visibility_limited: bool


class AssuranceNeighborhoodNode(AssuranceNodeRecord):
    """A node reached by a traversal, with how far out it was reached.

    ``hop`` is the distance from the root, so a client can render rings or fade by depth without
    recomputing the traversal it was just given. ``is_root`` is stated rather than derived by comparing
    against ``root_id``: the root is in the node list like any other node, and a reader that has to
    know which one it is should not have to join two fields to find out.
    """

    hop: int
    is_root: bool


class AssuranceNeighborhoodEdge(AssuranceEnrichedEdge):
    """An edge crossed by a traversal, from the perspective of the node it was crossed from.

    ``direction`` is relative to that node, which is why ``self`` is one of its values: a self-edge is
    neither incoming nor outgoing, and folding it into either would make a rendered graph disagree with
    the degree counts on the same node.
    """

    hop: int
    direction: Literal["outgoing", "incoming", "self"]


class AssuranceNeighborhoodResponse(_Closed):
    """One node's neighbourhood, as far as the budgets and the reader's ceiling allow.

    ``truncated`` and ``frontier_node_ids`` are the two halves of one fact: the traversal stopped early,
    and these are the nodes it stopped at. A client can offer to expand from exactly those rather than
    re-running the whole traversal with a larger hop count.

    ``max_hops`` is the budget that was *applied* after clamping, not what the caller asked for — a
    request for fifty hops against a ceiling of five is answered, and the answer says five.

    Exceeding the wall-clock budget is not represented here at all: it aborts with a retryable 503
    rather than returning a partial graph, because a partial traversal is not deterministic and a client
    cannot tell one from a complete small neighbourhood.
    """

    root_id: str
    nodes: list[AssuranceNeighborhoodNode]
    edges: list[AssuranceNeighborhoodEdge]
    truncated: bool
    frontier_node_ids: list[str]
    max_hops: int
    visibility_limited: bool


class AssuranceEdgeTypeOption(_Closed):
    """One connection type an edge may have, with the phrase a picker shows for it."""

    name: str
    label: str


class AssuranceEdgeTypePair(_Closed):
    """The connection types legal between one (source, target) node-type pair.

    Grouped per pair rather than served as a flat legality table, because a picker's question is
    always "given these two ends, what may I draw?" — and answering it from a flat table means the
    client re-deriving the grouping the module already knows.
    """

    source_type: str
    target_type: str
    connection_types: list[str]


class AssuranceReferenceTypeOption(_Closed):
    """One architecture-reference type, with what it means."""

    name: str
    description: str


class AssuranceEdgeCatalogResponse(_Closed):
    """The edge and reference vocabularies of the loaded assurance module.

    Edge types and reference types are kept apart, and that separation is a module invariant rather
    than a presentation choice: they are disjoint sets, and a reference type submitted as an edge type
    would create a relation the graph rules do not define. One list would invite exactly that.

    Module configuration, not store content — which is why this route is configured-gated and not
    unlock-gated, and answers ``not_configured`` when the module is absent.
    """

    edge_types: list[AssuranceEdgeTypeOption]
    permitted: list[AssuranceEdgeTypePair]
    reference_types: list[AssuranceReferenceTypeOption]


class AssuranceEdgeCreatedResponse(_Closed):
    """The edge that was created, named by the id the store minted for it.

    ``verification_findings`` rides along when the post-write verify found something. Advisory: the
    edge exists either way, and a finding blocks sign-off rather than the write.
    """

    edge_id: str
    source_id: str
    target_id: str
    conn_type: str
    verification_findings: list[AssuranceVerificationFinding] | None = None


class ModelThisTaskStep(_Closed):
    """One step of the separation-of-duties task: which tool to call, where, and with what.

    ``params`` belongs to the tool being called, not to this surface — three different tools appear
    across the three steps — so it is not mirrored here (see ``contracts/open_models.py``). Restating
    each tool's signature would make this DTO the place every one of their changes has to be echoed.

    ``note`` is present only where a step needs a caveat the parameters cannot express — step one has
    to be previewed with ``dry_run`` before it is committed, and its result feeds step two.
    """

    call: str
    on_server: str
    params: dict[str, Any]
    note: str | None = None


class ModelThisTaskRequiredResponse(_Closed):
    """The work to do, for a caller that may not create architecture entities itself.

    Separation of duties is the reason this exists: an assurance session with no architecture-write
    authority cannot mint the entity, so it is handed the three calls that will — create, bind, then
    mark the node bound — rather than a refusal. The steps are ordered and step two consumes step one's
    result, which is why they are named rather than a list.
    """

    outcome: Literal["task_required"]
    assurance_node_id: str
    assurance_node_name: str
    action_required: str
    step_1: ModelThisTaskStep
    step_2: ModelThisTaskStep
    step_3: ModelThisTaskStep
    note: str | None = None


class ModelThisBoundResponse(_Closed):
    """The architecture entity that was created and bound to the assurance node."""

    outcome: Literal["bound"]
    assurance_node_id: str
    arch_artifact_id: str
    verification_findings: list[AssuranceVerificationFinding] | None = None


class ModelThisResponse(RootModel[ModelThisBoundResponse | ModelThisTaskRequiredResponse]):
    """What ``POST /api/assurance/model-this`` answers: it either did the work or handed it over.

    A genuine union rather than two addresses, because the caller does not choose the path by URL —
    ``separation_of_duties`` in the body decides it, and both arms are successes of one operation.

    A ``RootModel`` rather than a bare ``A | B`` annotation so the document carries a *named* component:
    an inline union is a shape a generated client cannot refer to, and the response-contract fitness
    function refuses it for that reason. Discriminated on ``outcome``, so the schema is honestly
    ``oneOf`` with a discriminator rather than "one of these, work out which".
    """

    root: ModelThisBoundResponse | ModelThisTaskRequiredResponse = Field(discriminator="outcome")
