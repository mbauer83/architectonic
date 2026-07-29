"""The criteria engine: reusable condition trees for viewpoint query filtering, neighbor
inclusion, and style-rule matching.

``EntityCriteriaGroup``/``ConnectionCriteriaGroup`` are the ONE condition-building concept
used everywhere a boolean tree of attribute predicates appears — query filters, style-rule
``mode="match"`` criteria, and matrix axis criteria all reuse these same types rather than
parallel structures. Pure shapes only: parsing lives in ``viewpoint_criteria_parsing.py``,
registry-aware validation in ``viewpoint_criteria_validation.py``, evaluation semantics are
implemented by the evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND

Conjunction = Literal["and", "or"]
Comparator = Literal["eq", "neq", "in", "not_in", "exists", "absent", "lt", "lte", "gt", "gte", "like", "ilike"]
ValueRefKind = Literal["literal", "attribute_of_self", "attribute_of_endpoint", "binding", "parameter"]
IncidentDirection = Literal["outgoing", "incoming", "either"]
RelationshipTraversal = Literal["direct", "derived"]
IncidentTraversal = Literal["direct", "derived", "both"]

# Not every comparator needs a negated dual — `exists`/`absent` already form the
# null/not-null pair via `negate`. `not_in` is the deliberate exception: list membership
# is common enough, and reads badly as `negate` + `in`, that it earns a direct spelling.
# `like` (case-sensitive) and `ilike` (case-insensitive) add SQL-style pattern matching —
# `%` matches any run of characters, `_` matches exactly one, `\` escapes either.
NUMERIC_OPERATORS: frozenset[str] = frozenset({"lt", "lte", "gt", "gte"})
STRING_PATTERN_OPERATORS: frozenset[str] = frozenset({"like", "ilike"})
NUMERIC_ATTRIBUTE_TYPES: frozenset[str] = frozenset({"integer", "number", "date"})
# `slug` is a lexical REFINEMENT of `string`, not a separate value space: every slug is a
# string, and nothing enforces slug form at runtime (scalar binding accepts any ``str``), so
# the two compare and pattern-match interchangeably. The distinction is kept as an AUTHORING
# signal — it tells a surface to offer a slug field or a picker instead of free text — never
# as a comparison barrier. Keeping them incompatible made slug-typed parameters unusable
# against the reserved `group`/`specialization` paths, which resolve as plain strings.
# If slug ever gains real lexical validation, enforce it on the VALUE at bind time; do not
# re-tighten this lattice, or the same dead end returns.
STRING_LIKE_ATTRIBUTE_TYPES: frozenset[str] = frozenset({"string", "slug"})
STRING_ATTRIBUTE_TYPES: frozenset[str] = STRING_LIKE_ATTRIBUTE_TYPES

# Types the ordering comparators accept. Numbers and dates order by value; an ordinal orders by
# its declared rank. Whether two ordinals are drawn from the SAME scale is a separate question
# this set cannot answer — it is settled where the attribute schema is in scope.
ORDERED_ATTRIBUTE_TYPES: frozenset[str] = NUMERIC_ATTRIBUTE_TYPES | frozenset({ORDINAL_KIND})


def scalar_kinds_comparable(left: str, right: str) -> bool:
    """Whether two scalar kinds may be compared: identical kinds, or any two string-like ones.

    Two ordinals pass this kind-level check; that they are drawn from the same enum is enforced
    where the scales themselves are available, since a kind name cannot carry them.
    """
    return left == right or (left in STRING_LIKE_ATTRIBUTE_TYPES and right in STRING_LIKE_ATTRIBUTE_TYPES)
VALID_COMPARATORS: frozenset[str] = (
    frozenset({"eq", "neq", "in", "not_in", "exists", "absent"}) | NUMERIC_OPERATORS | STRING_PATTERN_OPERATORS
)
VALID_VALUE_REF_KINDS: frozenset[str] = frozenset(
    {"literal", "attribute_of_self", "attribute_of_endpoint", "binding", "parameter"}
)
VALID_INCIDENT_DIRECTIONS: frozenset[str] = frozenset({"outgoing", "incoming", "either"})
VALID_CONJUNCTIONS: frozenset[str] = frozenset({"and", "or"})

# Addressable properties: reserved read-model paths, resolved before
# the effective schema. None are numeric/date, so numeric comparators are always a save-mode
# error against a reserved path (`version` is explicitly "string comparators only").
RESERVED_ENTITY_PATHS: frozenset[str] = frozenset(
    {"id", "name", "type", "specialization", "group", "domain", "subdomain", "status", "version"}
)
RESERVED_CONNECTION_PATHS: frozenset[str] = frozenset({"id", "type", "specialization"})


@dataclass(frozen=True)
class ValueRef:
    """A condition's comparison value: a literal, or a reference to another attribute.

    ``attribute_of_self`` compares against another attribute on the SAME entity/connection
    being evaluated (e.g. ``end_date >= start_date``). ``attribute_of_endpoint`` is valid
    only within a connection condition, and reads an attribute off the source or target
    entity (e.g. ``strength >= target.threshold``).
    """

    kind: ValueRefKind = "literal"
    literal: object = None
    attribute: str | None = None  # required when kind != "literal"
    endpoint: Literal["source", "target"] | None = None  # required when kind == "attribute_of_endpoint"
    binding: str | None = None
    parameter: str | None = None
    project: str | None = None
    aggregate: Literal["count", "sum", "avg", "min", "max"] | None = None
    quantifier: Literal["any", "all"] | None = None


@dataclass(frozen=True)
class AttributeCondition:
    attribute: str  # dotted path
    comparator: Comparator
    value: ValueRef = ValueRef()
    negate: bool = False  # strict logical complement, including a missing attribute


@dataclass(frozen=True)
class EntityCriteriaGroup:
    conjunction: Conjunction = "and"
    children: "tuple[AttributeCondition | IncidentConnectionCondition | EntityCriteriaGroup, ...]" = ()
    negate: bool = False


@dataclass(frozen=True)
class ConnectionCriteriaGroup:
    conjunction: Conjunction = "and"
    children: "tuple[AttributeCondition | ConnectionCriteriaGroup, ...]" = ()
    negate: bool = False


@dataclass(frozen=True)
class IncidentConnectionCondition:
    """Entity-only predicate: "this entity has (or, negated, does not have) at least one
    incident connection matching ``connection_criteria``/``direction`` whose OTHER endpoint
    matches ``endpoint_criteria``." Fully criteria-based on both legs of the hop; recursive
    via ``endpoint_criteria``, bounded by save-time depth-cap validation.
    """

    connection_criteria: ConnectionCriteriaGroup | None = None  # None = any connection
    direction: IncidentDirection = "either"
    endpoint_criteria: EntityCriteriaGroup | None = None  # None = any entity
    negate: bool = False
    # "both" is the union of the direct and derived incident sets, computed BEFORE any
    # negation (a negated "both" predicate excludes entities with EITHER kind of connection).
    traversal: IncidentTraversal = "direct"
    include_potential: bool = False
    max_hops: int | None = None


@dataclass(frozen=True)
class ConnectionSelection:
    """Which connections a query displays, within the structural invariant: a
    connection is included only if both its source and target entities are in the included
    entity set. ``criteria`` narrows within that set; it can never widen past it.
    """

    enabled: bool = True
    criteria: ConnectionCriteriaGroup = ConnectionCriteriaGroup()
    traversal: Literal["direct", "derived", "both"] = "direct"
    include_potential: bool = False
    max_hops: int | None = None


@dataclass(frozen=True)
class NeighborInclusion:
    """Additive population term: include entities matching ``neighbor_criteria`` that
    are connected — by a connection matching ``connection_criteria``, in ``direction``
    relative to the anchor — to at least one entity of the query's PRIMARY result set.
    Anchors are always the primary set; inclusions never chain off other inclusions' results.
    """

    connection_criteria: ConnectionCriteriaGroup | None = None  # None = any connection
    direction: IncidentDirection = "either"  # relative to the anchor
    neighbor_criteria: EntityCriteriaGroup | None = None  # None = any entity
    traversal: RelationshipTraversal = "direct"
    include_potential: bool = False
    max_hops: int | None = None


EntityCriteriaNode = AttributeCondition | IncidentConnectionCondition | EntityCriteriaGroup
ConnectionCriteriaNode = AttributeCondition | ConnectionCriteriaGroup
