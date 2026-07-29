"""Bridge the trace mechanism into viewpoint execution: given the query's declared trace
patterns and the already-materialized row population, build the execution-scoped index and
produce the ``TraceTable``.

Kept out of ``evaluate_viewpoint`` so that module stays within the length policy and the trace
integration is one testable seam. The ``ModuleCatalog`` and the derivation budget come off the
injected ``RegistrySnapshot`` (``derivation_catalog`` + ``derivation_*``) — the SAME budget
object viewpoint execution uses generally, never a service-locator lookup.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.viewpoints.ports import RepositoryReadAccess
from src.application.viewpoints.trace_index import build_trace_graph_index
from src.application.viewpoints.trace_pipeline import TraceTable, evaluate_trace_table
from src.application.viewpoints.trace_realizers import eligible_realizer_types
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_trace_pattern_validation import expand_branch_edges
from src.domain.viewpoints.viewpoint_trace_patterns import DerivedReachabilityLeaf, InlineBranches
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery


def evaluate_declared_trace_table(
    query: ExecutableViewpointQuery,
    row_ids: tuple[str, ...],
    *,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
    bound_parameters: Mapping[str, object],
    limit: int | None,
) -> TraceTable | None:
    """Return the trace table for a query that declares trace patterns, else ``None``. Requires
    the derivation catalog (present whenever the runtime registry snapshot is built)."""
    patterns = query.trace_patterns
    if not patterns.patterns or registries.derivation_catalog is None:
        return None
    bounds = DerivationBounds(
        max_hops=registries.derivation_max_hops,
        max_relationships=registries.derivation_max_relationships,
        time_budget_seconds=registries.derivation_time_budget_seconds,
    )
    index = build_trace_graph_index(
        read_access,
        registries.derivation_catalog,
        referenced_connection_types=_referenced_connection_types(query),
        requirement_type=_terminal_type(query),
        bounds=bounds,
    )
    return evaluate_trace_table(
        row_ids,
        patterns=patterns,
        index=index,
        eligible=eligible_realizer_types(registries.derivation_catalog),
        gaps_only=bool(bound_parameters.get("gaps_only", False)),
        limit=limit,
    )


def _referenced_connection_types(query: ExecutableViewpointQuery) -> frozenset[str]:
    """Every connection type the patterns walk — branch/shortcut edges + derived leaves — so
    the index builds adjacency over exactly those and nothing else."""
    connections: set[str] = set()
    for pattern in query.trace_patterns.patterns:
        if isinstance(pattern.branches, InlineBranches):
            connections.update(named.edge.connection for named in pattern.branches.edges)
        connections.update(edge.connection for edge in pattern.shortcuts)
        if isinstance(pattern.leaf, DerivedReachabilityLeaf):
            connections.add(pattern.leaf.connection)
    return frozenset(connections)


def _terminal_type(query: ExecutableViewpointQuery) -> str:
    """The chain's terminal entity type (the leaf/obligation subject) — the endpoint of the
    last branch edge, derived from the grammar rather than hardcoded."""
    for pattern in query.trace_patterns.patterns:
        edges = expand_branch_edges(pattern, query.trace_patterns)
        if edges:
            return edges[-1].edge.endpoint_type
    return "requirement"
