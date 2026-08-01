"""The criteria tree: the one boolean-predicate language every part of a viewpoint filters with.

Query filters, neighbour inclusion, style-rule ``match`` criteria and matrix axes all reuse these
same shapes rather than parallel ones, exactly as the domain does — so this module is where the
definition language's recursion lives, and the query and presentation contracts build on it.

Closed at every level, which decision 6 asks for and the GUI editor already showed was possible: it
enumerates every node kind to round-trip an edit, so "this shape is open" was never true of the
language, only unstated. Nodes are discriminated by ``kind`` because a group and a condition sit at
the same position in ``children`` and nothing else tells them apart.

Field defaults are **omitted on the wire**, matching the canonical serialization a definition
round-trips through ``.arch-repo/viewpoints.yaml``: writing back every default would rewrite files
nobody edited. Every optional here is therefore absent-or-value, never null.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class ParameterValueRef(NullsOmitted):
    """Compare against a named execution parameter's bound value."""

    from_: Literal["parameter"] = Field(alias="from")
    name: str


class BindingValueRef(NullsOmitted):
    """Compare against a named binding's result.

    ``quantifier`` decides what a set-valued binding means in a scalar comparison — ``any`` member
    or ``all`` of them — and leaving it unset is not a third answer, it is the binding being
    single-valued.
    """

    from_: Literal["binding"] = Field(alias="from")
    name: str
    project: str | None = None
    aggregate: Literal["count", "sum", "avg", "min", "max"] | None = None
    quantifier: Literal["any", "all"] | None = None


class AttributeValueRef(NullsOmitted):
    """Compare against another attribute rather than a literal.

    ``self`` reads the record being evaluated (``end_date >= start_date``); ``source`` and
    ``target`` read an endpoint of the connection being evaluated, and mean nothing outside one.
    """

    from_: Literal["self", "source", "target"] = Field(alias="from")
    attribute: str


#: The three reference forms, told apart by ``from``. No ``Field(discriminator=...)``: the attribute
#: arm answers to three values of the tag, and pydantic silently skips the discriminator rather than
#: mapping a many-to-one tag — leaving a warning and an Input/Output schema split behind it. The arms
#: are closed and their tags are ``const``, so resolution does not need the mapping.
ValueRefResponse = ParameterValueRef | BindingValueRef | AttributeValueRef

#: A condition's comparison value: one of the references above, or a literal. A literal is a scalar
#: or a list of them, because that is what the comparators take — the membership operators want a
#: list and every other operator wants a single value.
ConditionValue = ValueRefResponse | str | int | float | bool | list[str | int | float | bool] | None

Comparator = Literal[
    "eq", "neq", "in", "not_in", "exists", "absent", "lt", "lte", "gt", "gte", "like", "ilike"
]
Conjunction = Literal["and", "or"]
IncidentDirection = Literal["outgoing", "incoming", "either"]


class AttributeConditionNode(NullsOmitted):
    """One attribute predicate.

    ``negate`` is a strict logical complement, a missing attribute included — so a negated ``eq``
    matches a record with no such attribute at all, which is deliberately not what ``neq`` does.

    ``value`` is absent where the comparator takes none (``exists``, ``absent``), which is the same
    spelling the canonical form uses for a condition whose value is left at its default.
    """

    kind: Literal["condition"]
    attribute: str
    comparator: Comparator
    value: ConditionValue = None
    negate: bool | None = None


class IncidentConnectionNode(NullsOmitted):
    """"This entity has an incident connection matching ``connection_criteria`` whose other
    endpoint matches ``endpoint_criteria``" — recursive on both legs, bounded by the save-time
    depth cap.

    ``traversal`` is written even at its default, unlike every other field here: it is load-bearing
    semantics, and stating it keeps a saved recipe stable if the default ever moves. ``both`` is the
    union of the direct and derived sets taken *before* negation, so a negated ``both`` excludes an
    entity that has either kind of connection.
    """

    kind: Literal["incident"]
    traversal: Literal["direct", "derived", "both"]
    direction: IncidentDirection | None = None
    connection_criteria: "ConnectionCriteriaGroupNode | None" = None
    endpoint_criteria: "EntityCriteriaGroupNode | None" = None
    negate: bool | None = None
    include_potential: bool | None = None
    max_hops: int | None = None


class EntityCriteriaGroupNode(NullsOmitted):
    """A conjunction or disjunction of entity predicates, itself negatable."""

    kind: Literal["group"]
    conjunction: Conjunction
    children: list["EntityCriteriaNode"]
    negate: bool | None = None


class ConnectionCriteriaGroupNode(NullsOmitted):
    """The connection-side group.

    Its children are conditions and groups only. An incident predicate asks what edges a thing has,
    and a connection has none of its own — which is why the two sides are separate types rather than
    one type with a context flag.
    """

    kind: Literal["group"]
    conjunction: Conjunction
    children: list["ConnectionCriteriaNode"]
    negate: bool | None = None


EntityCriteriaNode = Annotated[
    AttributeConditionNode | IncidentConnectionNode | EntityCriteriaGroupNode,
    Field(discriminator="kind"),
]
ConnectionCriteriaNode = Annotated[
    AttributeConditionNode | ConnectionCriteriaGroupNode, Field(discriminator="kind")
]


class NeighborInclusionSpec(NullsOmitted):
    """An additive population term: pull in entities connected to the primary result set.

    Anchors are always the primary set — an inclusion never chains off another inclusion's results,
    so a second term widens the population by one step and never by two.
    """

    direction: IncidentDirection | None = None
    connection_criteria: ConnectionCriteriaGroupNode | None = None
    neighbor_criteria: EntityCriteriaGroupNode | None = None
    traversal: Literal["direct", "derived"] | None = None
    include_potential: bool | None = None
    max_hops: int | None = None


class ConnectionSelectionSpec(NullsOmitted):
    """Which of the selected entities' connections the result displays.

    It narrows within the structural invariant and can never widen past it: a connection appears
    only when both its endpoints are already in the entity set, whatever ``criteria`` says.
    """

    enabled: bool | None = None
    criteria: ConnectionCriteriaGroupNode | None = None
    traversal: Literal["direct", "derived", "both"] | None = None
    include_potential: bool | None = None
    max_hops: int | None = None


IncidentConnectionNode.model_rebuild()
EntityCriteriaGroupNode.model_rebuild()
ConnectionCriteriaGroupNode.model_rebuild()
