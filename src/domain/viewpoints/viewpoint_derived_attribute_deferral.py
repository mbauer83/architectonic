"""Splits a query's declared derived attributes into the subset actually referenced by a
criteria tree (which must stay computed eagerly, over the full scoped candidate population,
since matching can't be decided without them) and the subset that is not (which is only
ever consumed by presentation — style tokens, label attributes — for whichever entities
survive filtering).

Per the evaluation-pipeline contract, derived attributes are meant to be computed lazily,
memoized per (entity, attribute) — never for entities the query has no other reason to
touch. A presentation-only derived attribute (the common case: a heat-map `scale_attribute`
that never appears in a condition) has no bearing on which entities match, so eagerly
evaluating it for the entire scoped population before filtering is pure waste — and each
evaluation of a `traversal: derived` attribute is a full bounded relationship-derivation
search, so that waste scales with population size times per-entity derivation cost, not
with the (usually much smaller) number of entities that actually end up in the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery

_DERIVED_PATH_PREFIX = "derived."


def _referenced_names(node: object) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, AttributeCondition):
        if node.attribute.startswith(_DERIVED_PATH_PREFIX):
            return {node.attribute[len(_DERIVED_PATH_PREFIX) :]}
        return set()
    if isinstance(node, (EntityCriteriaGroup, ConnectionCriteriaGroup)):
        names: set[str] = set()
        for child in node.children:
            names |= _referenced_names(child)
        return names
    if isinstance(node, IncidentConnectionCondition):
        return _referenced_names(node.connection_criteria) | _referenced_names(node.endpoint_criteria)
    return set()


def derived_attribute_names_referenced_in_criteria(query: ExecutableViewpointQuery) -> frozenset[str]:
    """Every `derived.<name>` reference across the trees that decide population
    membership: the primary entity criteria, every neighbor inclusion's connection/
    neighbor criteria, and the displayed-connections criteria. A derived attribute's own
    criteria and every binding's criteria are excluded by construction — both are
    validated to never reference `derived.` paths (no recursion, no forward reference)."""
    names = _referenced_names(query.entity_criteria)
    for inclusion in query.include_connected:
        names |= _referenced_names(inclusion.connection_criteria)
        names |= _referenced_names(inclusion.neighbor_criteria)
    names |= _referenced_names(query.connections.criteria)
    return frozenset(names)


@dataclass(frozen=True)
class DerivedAttributePartition:
    """Execution plan for a query's derived attributes: eager vs deferred (the
    criteria-referenced split) crossed with graph vs security-signal (the source
    split — signal attributes never reach the pure graph evaluator; the
    application orchestration batch-fetches them instead)."""

    eager_graph: tuple[DerivedAttribute, ...]
    deferred_graph: tuple[DerivedAttribute, ...]
    eager_signal: tuple[DerivedAttribute, ...]
    deferred_signal: tuple[DerivedAttribute, ...]


def split_eager_and_deferred_derived_attributes(
    query: ExecutableViewpointQuery,
) -> tuple[tuple[DerivedAttribute, ...], tuple[DerivedAttribute, ...]]:
    """`(eager, deferred)` — `eager` are referenced by a criteria tree and must be
    evaluated over the full scoped candidate set before filtering; `deferred` are not and
    should only ever be evaluated for the entities that end up in the retained population
    (presentation consumes them there)."""
    partition = partition_derived_attributes(query)
    return partition.eager_graph, partition.deferred_graph


def partition_derived_attributes(query: ExecutableViewpointQuery) -> DerivedAttributePartition:
    referenced = derived_attribute_names_referenced_in_criteria(query)
    graph = tuple(a for a in query.derived if a.source == "graph")
    signal = tuple(a for a in query.derived if a.source == "security-signal")
    return DerivedAttributePartition(
        eager_graph=tuple(a for a in graph if a.name in referenced),
        deferred_graph=tuple(a for a in graph if a.name not in referenced),
        eager_signal=tuple(a for a in signal if a.name in referenced),
        deferred_signal=tuple(a for a in signal if a.name not in referenced),
    )

def declares_signal_source(definition: object) -> bool:
    """Whether a viewpoint definition declares any security-signal derived
    attribute — the semantic trigger for persistence refusal: output styled by
    signal values is classification-bearing and ephemeral, so applying such a
    viewpoint to a git-persisted artifact is refused REGARDLESS of whether
    values happened to resolve."""
    query = getattr(definition, "query", None)
    if query is None:
        return False
    return any(attribute.source == "security-signal" for attribute in query.derived)
