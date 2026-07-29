"""Scale-adaptive aggregation of an execution's population into group/domain/type
super-nodes with bundled inter-aggregate edges — the server-side overview for results
beyond a presentation's legibility budget.

Identity and homogeneity are structural: a node aggregate is keyed by (dimension,
dimension value, entity type); an edge aggregate by (source aggregate, target aggregate,
connection type, provenance class). Because the key IS the bundle, no aggregate can mix
modeled and derived edges, mix connection types, or span more than one endpoint pair —
and two same-typed edges between different aggregate pairs always stay two bundles
(topology preservation). Aggregation always operates on the COMPLETE population, never a
truncated page; callers must aggregate before applying any entity/connection limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AggregationDimension = Literal["group", "domain", "type"]
AGGREGATION_DIMENSIONS: frozenset[str] = frozenset({"group", "domain", "type"})

EdgeProvenance = Literal["modeled", "derived-certain", "derived-potential"]


@dataclass(frozen=True)
class AggregateMember:
    """One aggregatable entity: the summary fields every aggregation dimension reads."""

    entity_id: str
    entity_type: str
    group: str
    domain: str


@dataclass(frozen=True)
class AggregateConnection:
    """One aggregatable connection occurrence (modeled or derived)."""

    connection_id: str
    source: str
    target: str
    connection_type: str
    certainty: Literal["certain", "potential"] | None = None  # None = modeled


@dataclass(frozen=True)
class AggregateNode:
    """Immutable identity tuple = (dimension, dimension_value, entity_type)."""

    id: str
    dimension: AggregationDimension
    dimension_value: str
    entity_type: str
    member_count: int
    member_ids: tuple[str, ...]  # sorted — the stable drill-down reference


@dataclass(frozen=True)
class AggregateEdge:
    """Immutable identity tuple = (source_aggregate_id, target_aggregate_id,
    connection_type, provenance)."""

    id: str
    source_aggregate_id: str
    target_aggregate_id: str
    connection_type: str
    provenance: EdgeProvenance
    member_count: int
    member_connection_ids: tuple[str, ...]  # sorted


@dataclass(frozen=True)
class AggregationSummary:
    dimension: AggregationDimension
    legibility_budget: int
    nodes: tuple[AggregateNode, ...]
    edges: tuple[AggregateEdge, ...]


def connection_provenance(certainty: Literal["certain", "potential"] | None) -> EdgeProvenance:
    if certainty is None:
        return "modeled"
    return "derived-certain" if certainty == "certain" else "derived-potential"


def _dimension_value(member: AggregateMember, dimension: AggregationDimension) -> str:
    if dimension == "group":
        return member.group
    if dimension == "domain":
        return member.domain
    return member.entity_type


def _node_id(dimension: AggregationDimension, value: str, entity_type: str) -> str:
    return f"agg:{dimension}={value}:{entity_type}"


def aggregate_population(
    members: tuple[AggregateMember, ...],
    connections: tuple[AggregateConnection, ...],
    *,
    dimension: AggregationDimension,
    legibility_budget: int,
) -> AggregationSummary:
    """Aggregate the COMPLETE population along ``dimension``. Membership is conserved by
    construction (every member lands in exactly one node aggregate; every connection whose
    endpoints both aggregate lands in exactly one edge bundle)."""
    node_members: dict[tuple[AggregationDimension, str, str], list[str]] = {}
    node_id_by_entity: dict[str, str] = {}
    for member in members:
        value = _dimension_value(member, dimension)
        key = (dimension, value, member.entity_type)
        node_members.setdefault(key, []).append(member.entity_id)
        node_id_by_entity[member.entity_id] = _node_id(dimension, value, member.entity_type)

    nodes = tuple(
        AggregateNode(
            id=_node_id(key[0], key[1], key[2]),
            dimension=key[0],
            dimension_value=key[1],
            entity_type=key[2],
            member_count=len(ids),
            member_ids=tuple(sorted(ids)),
        )
        for key, ids in sorted(node_members.items())
    )

    edge_members: dict[tuple[str, str, str, EdgeProvenance], list[str]] = {}
    for connection in connections:
        source_aggregate = node_id_by_entity.get(connection.source)
        target_aggregate = node_id_by_entity.get(connection.target)
        if source_aggregate is None or target_aggregate is None:
            continue
        provenance = connection_provenance(connection.certainty)
        key = (source_aggregate, target_aggregate, connection.connection_type, provenance)
        edge_members.setdefault(key, []).append(connection.connection_id)

    edges = tuple(
        AggregateEdge(
            id=f"aggedge:{source}->{target}:{connection_type}:{provenance}",
            source_aggregate_id=source,
            target_aggregate_id=target,
            connection_type=connection_type,
            provenance=provenance,
            member_count=len(ids),
            member_connection_ids=tuple(sorted(ids)),
        )
        for (source, target, connection_type, provenance), ids in sorted(edge_members.items())
    )

    return AggregationSummary(
        dimension=dimension, legibility_budget=legibility_budget, nodes=nodes, edges=edges
    )


def resolve_aggregation_dimension(aggregate_by: str | None, group_by: str | None) -> AggregationDimension:
    """The dimension an over-budget execution aggregates along: the explicitly authored
    ``aggregate_by`` wins; else a ``group_by`` that names an aggregation dimension; else
    ``group`` (the project axis — the most decision-relevant default partition)."""
    for candidate in (aggregate_by, group_by):
        if candidate == "group" or candidate == "domain" or candidate == "type":  # noqa: PLR1714 — literal narrowing
            return candidate
    return "group"
