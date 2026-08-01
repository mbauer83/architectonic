"""What one viewpoint execution returns — the same contract for REST and both MCP tools.

Derived from :class:`~src.application.viewpoints.execution_result.ViewpointExecutionResult`, which
is the single DTO ``evaluate_viewpoint`` produces; no transport reshapes it, so this is a
transcription of that dataclass rather than a delivery-specific view of it.

Deliberately **unstyled**. Style tokens come from ``/api/viewpoints/execute-projection`` and its
:class:`ViewpointProjectionResponse`, never from here, so MCP content and GUI content cannot
disagree about what an execution selected.

Nulls are sent, not omitted: ``matrix_axes``, ``target_population``, ``aggregation`` and
``trace_table`` are each present-and-null when they do not apply, and the client decoders read them
as nullable rather than absent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.infrastructure.gui.contracts.viewpoint_trace import TraceTableResponse


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: What one bound parameter is worth. Not open: a parameter declares a scalar element kind
#: (``string``/``slug``/``date``/``entity-id`` bind as strings, ``integer``/``number`` as numbers,
#: ``boolean`` as a bool) and a cardinality, and a set-valued parameter canonicalizes to a tuple of
#: strings — so these five arms are the whole value space ``bind_parameters`` can produce.
BoundParameterValue = bool | int | float | str | list[str]


class WitnessStepResponse(_Closed):
    """One hop of a derived connection's witness chain, ordered source→target.

    ``direction`` says whether the underlying modelled edge was walked forwards or against its
    arrow; without it a chain reads as a path that does not exist in the model.
    """

    connection_id: str
    source: str
    target: str
    connection_type: str
    direction: Literal["forward", "reverse"]
    hop_index: int


class EntityItemSummaryResponse(_Closed):
    """One selected entity, summarised the same way for every surface.

    ``domain`` is carried here rather than looked up per entity because grouping and layered
    presentation both need it at the moment the result is laid out.
    """

    id: str
    name: str
    type: str
    specialization_slugs: list[str]
    group: str
    domain: str
    membership: Literal["primary", "expanded"]
    status: str
    version: str
    #: One entry per authored column source, resolved at this execution's snapshot; a source that
    #: does not resolve for this entity is explicitly null, so a renderer never re-fetches to fill a
    #: column. Null when the definition authors no columns.
    column_values: dict[str, Any] | None
    #: Modelled hop distance from the nearest anchor (0 = anchor, 1 = direct edge, N = shortest
    #: witness chain). Null when the execution is unanchored, or when nothing connects this entity
    #: to an anchor — an unranked state, never distance 0 or 1.
    anchor_modeled_distance: int | None
    #: Set when the criteria match rested on REQUIRED derived evidence: the shortest witness chain
    #: the verdict depended on. Null when the match holds on modelled facts alone.
    matched_via_derived_hops: int | None


class ConnectionItemSummaryResponse(_Closed):
    """One selected connection, modelled or derived.

    ``via_connection_ids`` is unordered membership and is not renderable as a path;
    ``witness_steps`` is the ordered walk. Empty steps on a derived connection means the chain
    could not be reconstructed, which surfaces show as "chain unavailable" rather than as no chain.
    """

    id: str
    type: str
    source: str
    target: str
    certainty: Literal["certain", "potential"] | None
    hops: int | None
    via_connection_ids: list[str]
    witness_steps: list[WitnessStepResponse]


class MatrixAxisIdsResponse(_Closed):
    """The row and column populations of a criteria-axes matrix.

    Sorted subsets of the result's own entity ids. Entities on neither axis are the complement and
    are derivable, so they are not repeated here.
    """

    row_entity_ids: list[str]
    column_entity_ids: list[str]


class TargetPopulationSummaryResponse(_Closed):
    """The full (pre-truncation) result classified against the definition's declared targets.

    ``incidental_type_counts`` are the types that arrived because something else pulled them in;
    ``structural_count`` is what the query's own structure added. Null on the execution when the
    target population is unknown — an undeclared query-mode definition, or an ad-hoc query — in
    which case a header shows plain counts and makes no absence claim.
    """

    target_types: list[str]
    target_count: int
    incidental_type_counts: dict[str, int]
    structural_count: int


class AggregateNodeResponse(_Closed):
    """A super-node standing for every member entity sharing one dimension value."""

    id: str
    dimension: Literal["group", "domain", "type"]
    dimension_value: str
    entity_type: str
    member_count: int
    member_ids: list[str]


class AggregateEdgeResponse(_Closed):
    """Every connection between two aggregates, bundled into one edge.

    ``provenance`` keeps a bundle of derived edges from reading as modelled fact.
    """

    id: str
    source_aggregate_id: str
    target_aggregate_id: str
    connection_type: str
    provenance: Literal["modeled", "derived-certain", "derived-potential"]
    member_count: int
    member_connection_ids: list[str]


class AggregationSummaryResponse(_Closed):
    """The collapsed view a graph surface opens with when the population exceeds its budget.

    Always computed over the COMPLETE population, independent of the entity limit, so the overview
    describes the result rather than its first page.
    """

    dimension: Literal["group", "domain", "type"]
    legibility_budget: int
    nodes: list[AggregateNodeResponse]
    edges: list[AggregateEdgeResponse]


class ViewpointExecutionResponse(_Closed):
    """One execution: what ran, what it selected, and how much of it was returned.

    ``slug``/``version`` are null for an ad-hoc query, which has no identity to report.
    ``entity_ids``/``connection_ids`` are the complete selected populations while ``entities``/
    ``connections`` carry only the returned page, so ``truncated`` and the four counts are what
    tell a reader whether they are looking at all of it.
    """

    slug: str | None
    version: int | None
    query_schema: int
    repo_scope: str
    executed_at: str
    index_generation: int | None
    entity_ids: list[str]
    connection_ids: list[str]
    entities: list[EntityItemSummaryResponse]
    connections: list[ConnectionItemSummaryResponse]
    total_entity_count: int
    returned_entity_count: int
    total_connection_count: int
    returned_connection_count: int
    truncated: bool
    entity_limit: int
    matrix_axes: MatrixAxisIdsResponse | None
    warnings: list[str]
    duration_ms: float
    query_summary: str
    #: Entity ids the execution was anchored on — the resolved ``entity-id`` parameter values a
    #: presentation marks, centres, and measures hop distance from.
    anchor_ids: list[str]
    target_population: TargetPopulationSummaryResponse | None
    aggregation: AggregationSummaryResponse | None
    #: The canonical values this execution actually ran with — defaults applied, sets canonicalised.
    #: Distinct from what the caller sent: this is what a shared URL has to reproduce and what
    #: export provenance records, so neither has to re-derive the binding.
    bound_parameters: dict[str, BoundParameterValue]
    trace_table: TraceTableResponse | None
