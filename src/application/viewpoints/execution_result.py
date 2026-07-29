"""``ViewpointExecutionResult``: the ephemeral, never-persisted DTO
``EvaluateViewpoint`` returns. Identical shape for REST and both MCP tools — one contract,
no per-transport reshaping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from src.application.viewpoints.trace_pipeline import TraceTable
from src.domain.viewpoints.viewpoint_aggregation import AggregationSummary
from src.domain.viewpoints.viewpoint_target_population import TargetPopulationSummary
from src.domain.viewpoints.viewpoint_witness_steps import WitnessStep

Membership = Literal["primary", "expanded"]


@dataclass(frozen=True)
class EntityItemSummary:
    """Fixed, non-customizable per-entity summary."""

    id: str
    name: str
    type: str
    specialization_slugs: tuple[str, ...]
    group: str
    domain: str
    """The ontology domain the entity's type belongs to. Carried on the summary because
    grouping and layered presentation both need it synchronously: a client that has to fetch
    it per entity cannot group by it at the moment it lays the result out."""
    membership: Membership
    status: str = ""
    version: str = ""
    column_values: Mapping[str, object] | None = None
    """Present when the definition authors table columns: one entry per column source,
    resolved server-side at the execution's snapshot. A source that does not resolve for
    this entity is explicitly ``None`` — renderers never re-fetch to fill a column."""
    anchor_modeled_distance: int | None = None
    """Modeled hop distance from the nearest anchor (0 = anchor, 1 = direct modeled edge,
    N = minimum derived witness-chain length). ``None`` when the execution is unanchored
    or the entity has no connecting edge to any anchor (unranked — presentations must
    style that as its own state, never as distance 0 or 1)."""
    matched_via_derived_hops: int | None = None
    """Set when this entity's criteria match REQUIRED derived-relationship evidence: the
    minimum witness-chain length the verdict rested on. ``None`` when the match holds on
    modeled facts alone — surfaces use this to tag results "matched via derived (N hops)"."""


@dataclass(frozen=True)
class ConnectionItemSummary:
    """Fixed, non-customizable per-connection summary."""

    id: str
    type: str
    source: str
    target: str
    certainty: Literal["certain", "potential"] | None = None
    hops: int | None = None
    via_connection_ids: tuple[str, ...] = ()
    witness_steps: tuple[WitnessStep, ...] = ()
    """Derived connections only: the witness chain as an ORDERED source-to-target walk
    (``via_connection_ids`` is unordered membership, never renderable as-is). Empty for
    modeled connections — and for a derived connection whose chain can no longer be
    reconstructed, which renderers must show as "chain unavailable", not as no chain."""


@dataclass(frozen=True)
class MatrixAxisIds:
    """Present iff the executed definition's presentation is a criteria-axes matrix.
    Sorted subsets of the result's returned entity ids; unrendered entities are the
    complement, derivable, so not duplicated here."""

    row_entity_ids: tuple[str, ...]
    column_entity_ids: tuple[str, ...]


@dataclass(frozen=True)
class ViewpointExecutionResult:
    """One execution's full result — identity/provenance, content, counts/truncation,
    optional matrix axes, warnings, and timing. Never persisted."""

    slug: str | None
    version: int | None
    query_schema: int
    repo_scope: str
    executed_at: str
    index_generation: int | None
    entity_ids: tuple[str, ...]
    connection_ids: tuple[str, ...]
    entities: tuple[EntityItemSummary, ...]
    connections: tuple[ConnectionItemSummary, ...]
    total_entity_count: int
    returned_entity_count: int
    total_connection_count: int
    returned_connection_count: int
    truncated: bool
    entity_limit: int
    matrix_axes: MatrixAxisIds | None
    warnings: tuple[str, ...]
    duration_ms: float
    query_summary: str
    anchor_ids: tuple[str, ...] = ()
    """Entity ids the execution was anchored on — resolved ``entity-id`` parameter values.
    Presentations use these to mark/center the anchor and derive hop distances."""
    target_population: TargetPopulationSummary | None = None
    """Classification of the FULL (pre-truncation) result against the definition's
    declared target population. ``None`` when the target population is UNKNOWN
    (undeclared query-mode definition, or an ad-hoc query) — headers must then show
    plain counts and make NO absence claims."""
    aggregation: AggregationSummary | None = None
    """Present when the complete population exceeds the effective legibility budget on a
    graph surface (exploration/diagram): the group/domain/type super-nodes and bundled
    inter-aggregate edges the surface opens with. Always computed over the COMPLETE
    population, independent of the entity limit."""
    bound_parameters: Mapping[str, object] = field(default_factory=dict)
    """The CANONICAL parameter values this execution actually ran with — defaults applied and
    set values normalised. Distinct from what the caller sent: it is what a shared URL must
    reproduce and what export provenance must record, so neither has to re-derive binding."""
    trace_table: TraceTable | None = None
    """Present only for a query that declares ``trace_patterns``: the branch-complete coverage
    rows (per-pattern PatternResults + composed row verdict), already gaps-filtered/sorted/
    paged. ``None`` for every ordinary viewpoint — the field is additive and inert otherwise."""
