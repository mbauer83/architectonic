"""Immutable value objects for query bindings, parameters, and derived attributes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.viewpoints.viewpoint_criteria import ConnectionCriteriaGroup, EntityCriteriaGroup, IncidentDirection
from src.domain.viewpoints.viewpoint_value_types import AggregateKind, BindingSelect, QueryResultType, ScalarKind

AttributeSource = Literal["graph", "security-signal"]
DerivedTraversal = Literal["direct", "derived"]


@dataclass(frozen=True)
class QueryBinding:
    name: str
    result_type: QueryResultType
    select: BindingSelect | None = None
    criteria: EntityCriteriaGroup | ConnectionCriteriaGroup | None = None
    project: str | None = None
    aggregate: AggregateKind | None = None
    tuple_of: tuple[str, ...] = ()
    include_in_result: bool = False


ParameterCardinality = Literal["one", "many"]


@dataclass(frozen=True)
class QueryParameter:
    """A declared execution parameter.

    ``value_type`` is the ELEMENT kind and ``cardinality`` the shape — deliberately
    orthogonal, so a set-valued parameter is not its own type name: a closed set of strings
    (the coverage ``scope``) and an open set of slugs (a ``group`` filter) differ only by
    ``allowed_values``, and future element kinds compose for free.

    ``allowed_values`` present = a CLOSED vocabulary, enforced at bind time. Absent = an OPEN
    vocabulary whose members are whatever the caller supplies (a nonexistent value yields an
    empty result rather than an error, so the filter never breaks on model change).
    """

    name: str
    value_type: ScalarKind | Literal["entity-id"]
    required: bool = True
    default: object = None
    description: str = ""
    cardinality: ParameterCardinality = "one"
    allowed_values: tuple[str, ...] = ()  # closed vocabulary; empty = open
    min_items: int = 0  # cardinality "many" only

    @property
    def is_set_valued(self) -> bool:
        return self.cardinality == "many"

    @property
    def has_closed_vocabulary(self) -> bool:
        return bool(self.allowed_values)


@dataclass(frozen=True)
class DerivedAttribute:
    name: str
    # Typed source discriminator: "graph" attributes are computed by the pure
    # graph evaluator; "security-signal" attributes are batch-fetched from the
    # signal-metrics capability by the application orchestration (the graph
    # fields below are meaningless for them and validated absent).
    source: AttributeSource = "graph"
    metric: str | None = None
    direction: IncidentDirection = "either"
    traversal: DerivedTraversal = "direct"
    include_potential: bool = False
    max_hops: int | None = None
    connection_criteria: ConnectionCriteriaGroup | None = None
    endpoint_criteria: EntityCriteriaGroup | None = None
    reduce: AggregateKind = "count"
    of: str | None = None
