"""A viewpoint definition as the management view reads it: the whole authored record, plus what the
server computed about it.

The definition language is served in its canonical form — the same mapping
``.arch-repo/viewpoints.yaml`` holds and the same one a save accepts back — so the editor loads and
returns one shape rather than translating between two. Defaults are omitted, as they are on write.

Closed at every level. The levels here are the definition's own fields, its query and its
presentation; the criteria tree they nest is in :mod:`viewpoint_criteria`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.infrastructure.rest.contracts.viewpoint_criteria import (
    ConnectionCriteriaGroupNode,
    ConnectionSelectionSpec,
    EntityCriteriaGroupNode,
    NeighborInclusionSpec,
)
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted

#: A scalar a parameter may declare a default or an allowed value as. The element kinds are
#: ``string``/``slug``/``date``/``entity-id`` (strings), ``integer``/``number`` and ``boolean``; a
#: set-valued parameter's default is a list of them.
ParameterLiteral = str | int | float | bool
AggregateKind = Literal["count", "min", "max", "sum", "average", "first", "last"]


class QueryBindingSpec(NullsOmitted):
    """A named sub-query whose result other conditions compare against.

    ``include_in_result`` promotes the bound entities into the result population; without it a
    binding is only a value to compare with, which is the difference between "the systems this
    depends on" as an answer and as a filter.
    """

    name: str
    #: A type *expression* rather than a closed vocabulary — ``entity[type-slug]``,
    #: ``list[result-type]`` and ``tuple[result-type, ...]`` are grammar with holes in them.
    result_type: str
    #: ``entities``/``connections``, the plural the domain's ``BindingSelect`` uses and the write
    #: path stores. The singular was declared here and never produced: the first definition saved
    #: with a binding made ``GET /api/viewpoints`` answer 500 for *every* caller — one write, and
    #: the whole catalogue unreadable — because the response model rejected the stored value.
    select: Literal["entities", "connections"] | None = None
    criteria: EntityCriteriaGroupNode | ConnectionCriteriaGroupNode | None = None
    project: str | None = None
    aggregate: AggregateKind | None = None
    #: Written as ``tuple`` in the canonical form; the component binding names, in order.
    tuple: list[str] | None = None
    include_in_result: bool | None = None


class QueryParameterSpec(NullsOmitted):
    """A declared execution parameter.

    ``type`` is the element kind and ``cardinality`` the shape, deliberately orthogonal: a closed
    set of strings and an open set of slugs differ only by ``allowed_values``, so a set-valued
    parameter is not its own type name.

    ``allowed_values`` present means a CLOSED vocabulary enforced at bind time. Absent means open —
    an unmatched value yields an empty result rather than an error, so a saved filter survives a
    model change.
    """

    name: str
    type: Literal["string", "integer", "number", "date", "boolean", "slug", "entity-id"]
    cardinality: Literal["one", "many"] | None = None
    allowed_values: list[str] | None = None
    min_items: int | None = None
    required: Literal[False] | None = None
    default: ParameterLiteral | list[ParameterLiteral] | None = None
    description: str | None = None


class DerivedAttributeSpec(NullsOmitted):
    """A computed attribute a condition or a column may address as ``derived.<name>``.

    Two sources, and the graph fields are meaningless for the other one: a ``security-signal``
    attribute is batch-fetched from the signal capability and carries only ``metric``, which is why
    that arm is validated to have none of the traversal fields set.
    """

    name: str
    source: Literal["security-signal"] | None = None
    metric: str | None = None
    direction: Literal["outgoing", "incoming", "either"] | None = None
    traversal: Literal["direct", "derived"] | None = None
    include_potential: bool | None = None
    max_hops: int | None = None
    connection_criteria: ConnectionCriteriaGroupNode | None = None
    endpoint_criteria: EntityCriteriaGroupNode | None = None
    reduce: AggregateKind | None = None
    of: str | None = None


class TraceEndpointTypeSpec(NullsOmitted):
    """The entity type a branch edge is expected to land on."""

    type: str


class TraceStoredEdgeSpec(NullsOmitted):
    """One branch of a trace pattern: which connection to walk, which way, and what it should reach."""

    kind: str
    connection: str
    direction: str
    endpoint: TraceEndpointTypeSpec


class TraceDiagnosticEdgeSpec(TraceStoredEdgeSpec):
    """A shortcut branch, carrying the status it reports when it is the only path found."""

    status: str


class TraceRegistryEndpointSpec(NullsOmitted):
    """A leaf endpoint named by the registry it must be declared in."""

    registry: str


class TraceLayerEndpointSpec(NullsOmitted):
    """A leaf endpoint named by ontology membership: a domain, optionally narrowed to a class."""

    domain: str
    #: Written as ``class`` in the canonical form, and absent for a whole-domain endpoint.
    class_: str | None = Field(default=None, alias="class")


class TraceLeafSpec(NullsOmitted):
    """How a pattern's chain terminates.

    ``kind`` ``none`` is a pattern with no reachability leaf at all; the derived-reachability leaf
    carries the connection to walk and the endpoint it must arrive at.
    """

    kind: str
    connection: str | None = None
    traversal: str | None = None
    max_hops: int | None = None
    endpoint: TraceRegistryEndpointSpec | TraceLayerEndpointSpec | None = None


class TraceBranchesRefSpec(NullsOmitted):
    """Branches shared by reference, preserved rather than expanded — expansion happens at
    evaluation, never on save, so a saved definition still shows which set it points at."""

    ref: str


class TracePatternSpec(NullsOmitted):
    """One branch-complete coverage pattern.

    ``branches`` is either a ``{"ref": ...}`` pointer or a map of branch label → edge; the labels
    are the pattern author's, which is why that arm is a map and not a list.

    ``diagnostic`` marks the pattern verdict-neutral: it observes, and its absence is neither a pass
    nor a gap.
    """

    name: str
    kind: str
    applies_to: list[str]
    branches: TraceBranchesRefSpec | dict[str, TraceStoredEdgeSpec]
    leaf: TraceLeafSpec
    shortcuts: list[TraceDiagnosticEdgeSpec] | None = None
    diagnostic: bool | None = None


class ViewpointQuerySpec(NullsOmitted):
    """The executable query: which entities, which of their connections, and what to compute.

    ``entity_criteria`` is always present — a query with no filter still says so with an empty
    group, because an absent criteria tree and one that matches everything are different claims.
    """

    query_schema: int
    entity_criteria: EntityCriteriaGroupNode
    include_connected: list[NeighborInclusionSpec] | None = None
    connections: ConnectionSelectionSpec | None = None
    repo_scope: Literal["enterprise", "engagement", "both"] | None = None
    bindings: list[QueryBindingSpec] | None = None
    parameters: list[QueryParameterSpec] | None = None
    derived: list[DerivedAttributeSpec] | None = None
    trace_patterns: list[TracePatternSpec] | None = None


class ColumnSpecResponse(NullsOmitted):
    """One table column: its heading, and the attribute path that fills it."""

    label: str
    source: str


class RangeBandSpec(NullsOmitted):
    """One band of a ``range`` style rule: ``minimum`` inclusive, ``maximum`` exclusive.

    Either end is absent when it is unbounded, which is exactly how the parser reads it back — so an
    omitted bound is "no bound here", never an unknown one.
    """

    minimum: float | None
    maximum: float | None
    value: str


class StyleRuleSpec(NullsOmitted):
    """One authored styling rule for one capability.

    Three modes, and each uses a different subset: ``match`` takes criteria and a token, ``range``
    takes an attribute and bands, ``scale`` takes an attribute, bounds and two gradient endpoints.
    Switching mode clears the others' fields, so a rule never carries two modes' worth of intent.

    ``disabled`` is quarantine: saveable exactly as inherited but never evaluated, which is how a
    fork keeps a rule whose attribute no longer resolves instead of silently dropping it.
    """

    capability: str
    applies_to: list[str] | None = None
    mode: Literal["range", "scale"] | None = None
    match_criteria: EntityCriteriaGroupNode | ConnectionCriteriaGroupNode | None = None
    value: str | None = None
    range_attribute: str | None = None
    range_bands: list[RangeBandSpec] | None = None
    scale_attribute: str | None = None
    scale_min: float | str | None = None
    scale_max: float | str | None = None
    scale_tokens: list[str] | None = None
    source_criteria: EntityCriteriaGroupNode | None = None
    target_criteria: EntityCriteriaGroupNode | None = None
    disabled: bool | None = None


class DisplayOptionsSpec(NullsOmitted):
    """The representation-gated rendering choices, each validated at save time.

    A closed set rather than a map: all three are enumerated vocabularies the validator checks, and
    an option it does not know is a save-time error rather than a hint a renderer might honour.
    """

    #: Exploration only.
    layout: Literal["clusters", "radial", "force"] | None = None
    #: Exploration only. What an unstyled node is filled by — declared, never inferred, because
    #: deriving it from the query's shape would recolour a view for anchoring it.
    color_by: Literal["domain", "hop-distance"] | None = None
    #: Exploration and diagram: the attribute path to label nodes with instead of the name.
    label_attribute: str | None = None


class PresentationSpecResponse(NullsOmitted):
    """How one representation renders the population.

    Additive on the query and never part of it: two presentations of one query select the same
    entities, so a summary or a count never depends on this level.
    """

    representation: Literal["exploration", "table", "matrix", "diagram"]
    display_options: DisplayOptionsSpec | None = None
    columns: list[ColumnSpecResponse] | None = None
    row_by: str | None = None
    column_by: str | None = None
    row_criteria: EntityCriteriaGroupNode | None = None
    column_criteria: EntityCriteriaGroupNode | None = None
    group_by: str | None = None
    #: Ordered, first match wins per capability — which is what makes a later rule *shadowed*
    #: rather than merged.
    styling_rules: list[StyleRuleSpec] | None = None
    #: Capability → the token used where no rule matched.
    default_style: dict[str, str] | None = None
    target_types: list[str] | None = None
    legibility_budget: int | None = None
    aggregate_by: str | None = None


class ConceptScopeSpec(NullsOmitted):
    """The declarative selection layer: which types are in and which are out.

    An absent ``entity_types``/``connection_types`` means unrestricted, which is why they are
    omitted rather than sent as an empty list — an empty list would select nothing.
    """

    entity_types: list[str] | None = None
    connection_types: list[str] | None = None
    excluded_entity_types: list[str] | None = None
    excluded_domains: list[str] | None = None
    excluded_connection_types: list[str] | None = None


class ForkLineageSpec(NullsOmitted):
    """Where a forked definition came from, stamped server-side at fork time."""

    slug: str
    version: int
    definition_digest: str
    index_generation: int | None = None


class ScopeSummaryResponse(NullsOmitted):
    """The scope in words, for a list row that has no space for the scope itself."""

    unrestricted: bool
    entity_types: list[str] | None = None
    connection_types: list[str] | None = None
    excluded_entity_types: list[str] | None = None
    excluded_domains: list[str] | None = None
    excluded_connection_types: list[str] | None = None


class BrokenReferenceResponse(NullsOmitted):
    """One reference in a definition that no longer resolves.

    Computed on demand and never persisted: it is a function of the definition and the current
    model, so storing it would mean storing a claim that goes stale the moment either changes.
    """

    kind: Literal["entity-type", "connection-type", "specialization", "attribute-path", "entity-id"]
    reference: str
    #: Human-readable, e.g. "entity criteria" or "style rule 2 (node_color)" — a place a person can
    #: find, not a machine path, because the editor shows it beside the field it names.
    locus: str
    #: Derived from ``kind``: an ontology reference broke because the model's vocabulary changed, an
    #: entity-id anchor because a specific entity is gone. The two want different repairs.
    severity: Literal["ontology", "entity-id"]


class ViewpointDefinitionEnvelope(NullsOmitted):
    """One catalogue entry: the authored definition, and what the server knows about it.

    The definition's own fields come first, in canonical form, so the editor can populate a form
    from this row without a second request. The rest is computed per request: which tier owns it
    (and therefore whether it is editable here), what its scope and query say in words, its current
    content digest, whether a fork has fallen behind its origin, and which of its references are
    broken.

    ``selection_mode`` says which of ``scope`` and ``query`` is *active*. It is absent on
    pre-migration definitions, where the legacy rule applies: the query when there is one, else the
    scope.
    """

    slug: str
    version: int
    name: str
    description: str | None = None
    rationale: str | None = None
    #: Written as a bare string for a single value and a list for several — the canonical shorthand,
    #: kept so a hand-edited catalogue file round-trips unchanged.
    purpose: str | list[str]
    content: str | list[str]
    stakeholders: list[str] | None = None
    concerns: list[str] | None = None
    scope: ConceptScopeSpec | None = None
    representation_types: list[str] | None = None
    #: Derivation limits this definition overrides, keyed by limit name. An open map with a
    #: scalar value: nothing in the engine reads it yet, so there is no key set to enumerate,
    #: and a limit is a number, a flag or a named strategy.
    derivation_defaults: dict[str, int | float | bool | str] | None = None
    query: ViewpointQuerySpec | None = None
    presentation: PresentationSpecResponse | None = None
    selection_mode: Literal["scope", "query"] | None = None
    forked_from: ForkLineageSpec | None = None
    tier: Literal["module", "enterprise", "engagement"]
    scope_summary: ScopeSummaryResponse
    #: Absent for a scope-mode definition with no active query — there is no query to summarise,
    #: which is not the same as a query that summarises to nothing.
    query_summary: str | None = None
    #: The CURRENT content digest. A verified execution pins it, and fork staleness is decided
    #: against it rather than against a version integer somebody hand-edits.
    definition_digest: str
    #: Absent for a definition that is not a fork.
    fork_status: Literal["current", "stale", "origin-missing"] | None = None
    broken_references: list[BrokenReferenceResponse]


class ViewpointDefinitionListResponse(NullsOmitted):
    """The effective merged catalogue: module, then enterprise, then engagement definitions."""

    viewpoints: list[ViewpointDefinitionEnvelope]
