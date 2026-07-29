"""Parsing for criteria trees: nodes are discriminated by
``kind: condition | incident | group``; a condition's ``value`` is either a literal
shorthand (plain scalar/list) or a ``{from: self|source|target, attribute: ...}`` mapping
(a ``ValueRef`` reference). Unknown keys are a parse error — never ignored.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from src.domain.viewpoints.viewpoint_criteria import (
    VALID_COMPARATORS,
    VALID_CONJUNCTIONS,
    VALID_INCIDENT_DIRECTIONS,
    AttributeCondition,
    Comparator,
    Conjunction,
    ConnectionCriteriaGroup,
    ConnectionCriteriaNode,
    ConnectionSelection,
    EntityCriteriaGroup,
    EntityCriteriaNode,
    IncidentConnectionCondition,
    IncidentDirection,
    IncidentTraversal,
    NeighborInclusion,
    RelationshipTraversal,
    ValueRef,
)

_CONDITION_KEYS = frozenset({"kind", "attribute", "comparator", "value", "negate"})
_GROUP_KEYS = frozenset({"kind", "conjunction", "children", "negate"})
_INCIDENT_KEYS = frozenset(
    {
        "kind",
        "direction",
        "connection_criteria",
        "endpoint_criteria",
        "negate",
        "traversal",
        "include_potential",
        "max_hops",
    }
)
_VALUE_REF_KEYS = frozenset({"from", "attribute", "name", "project", "aggregate", "quantifier"})
_NEIGHBOR_INCLUSION_KEYS = frozenset(
    {"connection_criteria", "direction", "neighbor_criteria", "traversal", "include_potential", "max_hops"}
)
_CONNECTION_SELECTION_KEYS = frozenset({"enabled", "criteria", "traversal", "include_potential", "max_hops"})


def _check_keys(raw: Mapping[str, object], allowed: frozenset[str], *, label: str) -> None:
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise ValueError(f"{label}: unknown key(s) {sorted(unknown)}")


def _require_comparator(value: object) -> Comparator:
    text = str(value)
    if text not in ("eq", "neq", "in", "not_in", "exists", "absent", "lt", "lte", "gt", "gte", "like", "ilike"):
        raise ValueError(f"comparator {text!r} is not one of {sorted(VALID_COMPARATORS)}")
    return text


def _require_conjunction(value: object) -> Conjunction:
    text = str(value)
    if text not in ("and", "or"):
        raise ValueError(f"conjunction {text!r} is not one of {sorted(VALID_CONJUNCTIONS)}")
    return text


def _require_direction(value: object) -> IncidentDirection:
    text = str(value)
    if text not in ("outgoing", "incoming", "either"):
        raise ValueError(f"direction {text!r} is not one of {sorted(VALID_INCIDENT_DIRECTIONS)}")
    return text


def _require_traversal(value: object) -> RelationshipTraversal:
    if value not in {"direct", "derived"}:
        raise ValueError("traversal must be direct or derived")
    return cast(RelationshipTraversal, value)


def _require_incident_traversal(value: object) -> IncidentTraversal:
    if value not in {"direct", "derived", "both"}:
        raise ValueError("traversal must be direct, derived, or both")
    return cast(IncidentTraversal, value)


def _optional_hops(raw: object) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 2:
        raise ValueError("max_hops must be an integer of at least 2")
    return raw


def _require_connection_traversal(value: object) -> Literal["direct", "derived", "both"]:
    if value not in {"direct", "derived", "both"}:
        raise ValueError("connection traversal must be direct, derived, or both")
    return cast(Literal["direct", "derived", "both"], value)


def _value_ref_from_raw(raw: object) -> ValueRef:
    if isinstance(raw, Mapping) and "from" in raw:
        _check_keys(raw, _VALUE_REF_KEYS, label="value reference")
        from_ = str(raw["from"])
        if from_ in {"binding", "parameter"}:
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"{from_} value reference requires 'name'")
            if from_ == "parameter":
                return ValueRef(kind="parameter", parameter=name)
            aggregate = raw.get("aggregate")
            quantifier = raw.get("quantifier")
            if aggregate not in {None, "count", "sum", "avg", "min", "max"}:
                raise ValueError("binding value reference has an unknown aggregate")
            if quantifier not in {None, "any", "all"}:
                raise ValueError("binding value reference has an unknown quantifier")
            return ValueRef(
                kind="binding",
                binding=name,
                project=str(raw["project"]) if raw.get("project") is not None else None,
                aggregate=aggregate,
                quantifier=quantifier,
            )
        if from_ not in ("self", "source", "target"):
            raise ValueError(f"value 'from' must be one of self/source/target/binding/parameter, got {from_!r}")
        attribute = raw.get("attribute")
        if not attribute:
            raise ValueError("value reference requires 'attribute'")
        if from_ == "self":
            return ValueRef(kind="attribute_of_self", attribute=str(attribute))
        return ValueRef(kind="attribute_of_endpoint", attribute=str(attribute), endpoint=from_)
    return ValueRef(kind="literal", literal=raw)


def _condition_from_raw(raw: Mapping[str, object]) -> AttributeCondition:
    _check_keys(raw, _CONDITION_KEYS, label="condition")
    return AttributeCondition(
        attribute=str(raw["attribute"]),
        comparator=_require_comparator(raw["comparator"]),
        value=_value_ref_from_raw(raw.get("value")),
        negate=bool(raw.get("negate", False)),
    )


def _children_from_raw(raw: object) -> tuple[object, ...]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("children must be a list")
    return tuple(raw)


def parse_entity_criteria_node(raw: object) -> EntityCriteriaNode:
    if not isinstance(raw, Mapping):
        raise ValueError("criteria node must be a mapping")
    kind = raw.get("kind")
    if kind == "condition":
        return _condition_from_raw(raw)
    if kind == "incident":
        return _incident_from_raw(raw)
    if kind == "group":
        return parse_entity_criteria_group(raw)
    raise ValueError(f"unknown entity criteria node kind {kind!r}")


def parse_entity_criteria_group(raw: object) -> EntityCriteriaGroup:
    if not isinstance(raw, Mapping) or raw.get("kind") != "group":
        raise ValueError("expected an entity criteria group (kind: group)")
    _check_keys(raw, _GROUP_KEYS, label="entity criteria group")
    children = tuple(parse_entity_criteria_node(child) for child in _children_from_raw(raw.get("children", [])))
    return EntityCriteriaGroup(
        conjunction=_require_conjunction(raw.get("conjunction", "and")),
        children=children,
        negate=bool(raw.get("negate", False)),
    )


def _incident_from_raw(raw: Mapping[str, object]) -> IncidentConnectionCondition:
    _check_keys(raw, _INCIDENT_KEYS, label="incident condition")
    connection_criteria_raw = raw.get("connection_criteria")
    endpoint_criteria_raw = raw.get("endpoint_criteria")
    return IncidentConnectionCondition(
        connection_criteria=parse_connection_criteria_group(connection_criteria_raw)
        if connection_criteria_raw is not None
        else None,
        direction=_require_direction(raw.get("direction", "either")),
        endpoint_criteria=parse_entity_criteria_group(endpoint_criteria_raw)
        if endpoint_criteria_raw is not None
        else None,
        negate=bool(raw.get("negate", False)),
        traversal=_require_incident_traversal(raw.get("traversal", "direct")),
        include_potential=bool(raw.get("include_potential", False)),
        max_hops=_optional_hops(raw.get("max_hops")),
    )


def parse_connection_criteria_node(raw: object) -> ConnectionCriteriaNode:
    if not isinstance(raw, Mapping):
        raise ValueError("criteria node must be a mapping")
    kind = raw.get("kind")
    if kind == "condition":
        return _condition_from_raw(raw)
    if kind == "group":
        return parse_connection_criteria_group(raw)
    raise ValueError(f"unknown connection criteria node kind {kind!r}")


def parse_connection_criteria_group(raw: object) -> ConnectionCriteriaGroup:
    if not isinstance(raw, Mapping) or raw.get("kind") != "group":
        raise ValueError("expected a connection criteria group (kind: group)")
    _check_keys(raw, _GROUP_KEYS, label="connection criteria group")
    children = tuple(parse_connection_criteria_node(child) for child in _children_from_raw(raw.get("children", [])))
    return ConnectionCriteriaGroup(
        conjunction=_require_conjunction(raw.get("conjunction", "and")),
        children=children,
        negate=bool(raw.get("negate", False)),
    )


def parse_neighbor_inclusion(raw: object) -> NeighborInclusion:
    if not isinstance(raw, Mapping):
        raise ValueError("neighbor inclusion must be a mapping")
    _check_keys(raw, _NEIGHBOR_INCLUSION_KEYS, label="neighbor inclusion")
    connection_criteria_raw = raw.get("connection_criteria")
    neighbor_criteria_raw = raw.get("neighbor_criteria")
    return NeighborInclusion(
        connection_criteria=parse_connection_criteria_group(connection_criteria_raw)
        if connection_criteria_raw is not None
        else None,
        direction=_require_direction(raw.get("direction", "either")),
        neighbor_criteria=parse_entity_criteria_group(neighbor_criteria_raw)
        if neighbor_criteria_raw is not None
        else None,
        traversal=_require_traversal(raw.get("traversal", "direct")),
        include_potential=bool(raw.get("include_potential", False)),
        max_hops=_optional_hops(raw.get("max_hops")),
    )


def parse_connection_selection(raw: object) -> ConnectionSelection:
    if raw is None:
        return ConnectionSelection()
    if not isinstance(raw, Mapping):
        raise ValueError("connections must be a mapping")
    _check_keys(raw, _CONNECTION_SELECTION_KEYS, label="connection selection")
    criteria_raw = raw.get("criteria")
    return ConnectionSelection(
        enabled=bool(raw.get("enabled", True)),
        criteria=parse_connection_criteria_group(criteria_raw)
        if criteria_raw is not None
        else ConnectionCriteriaGroup(),
        traversal=_require_connection_traversal(raw.get("traversal", "direct")),
        include_potential=bool(raw.get("include_potential", False)),
        max_hops=_optional_hops(raw.get("max_hops")),
    )
