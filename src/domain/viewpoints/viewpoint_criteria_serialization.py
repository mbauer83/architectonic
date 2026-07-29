"""Serialize criteria trees to their canonical YAML shape: field defaults are
omitted on write, ``negate`` is written only when true, and a condition's default
(``ValueRef()``) value is omitted entirely (matching the parser reading an absent ``value``
key as that same default) — the counterpart to ``viewpoint_criteria_parsing.py``.
"""

from __future__ import annotations

from typing import Any

from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    NeighborInclusion,
    ValueRef,
)


def _value_ref_to_raw(value: ValueRef) -> Any:
    if value.kind == "literal":
        return value.literal
    if value.kind == "parameter":
        return {"from": "parameter", "name": value.parameter}
    if value.kind == "binding":
        result: dict[str, Any] = {"from": "binding", "name": value.binding}
        if value.project is not None:
            result["project"] = value.project
        if value.aggregate is not None:
            result["aggregate"] = value.aggregate
        if value.quantifier is not None:
            result["quantifier"] = value.quantifier
        return result
    from_ = "self" if value.kind == "attribute_of_self" else value.endpoint
    return {"from": from_, "attribute": value.attribute}


def _condition_to_mapping(condition: AttributeCondition) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "condition", "attribute": condition.attribute, "comparator": condition.comparator}
    if condition.value != ValueRef():
        result["value"] = _value_ref_to_raw(condition.value)
    if condition.negate:
        result["negate"] = True
    return result


def entity_criteria_node_to_mapping(node: object) -> dict[str, Any]:
    if isinstance(node, AttributeCondition):
        return _condition_to_mapping(node)
    if isinstance(node, IncidentConnectionCondition):
        return _incident_to_mapping(node)
    if isinstance(node, EntityCriteriaGroup):
        return entity_criteria_group_to_mapping(node)
    raise TypeError(f"unrecognized entity criteria node: {node!r}")


def entity_criteria_group_to_mapping(group: EntityCriteriaGroup) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "group",
        "conjunction": group.conjunction,
        "children": [entity_criteria_node_to_mapping(c) for c in group.children],
    }
    if group.negate:
        result["negate"] = True
    return result


def _incident_to_mapping(condition: IncidentConnectionCondition) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "incident"}
    if condition.direction != "either":
        result["direction"] = condition.direction
    if condition.connection_criteria is not None:
        result["connection_criteria"] = connection_criteria_group_to_mapping(condition.connection_criteria)
    if condition.endpoint_criteria is not None:
        result["endpoint_criteria"] = entity_criteria_group_to_mapping(condition.endpoint_criteria)
    if condition.negate:
        result["negate"] = True
    # Always written, even at the default: a predicate's traversal is load-bearing
    # semantics, and an explicit value keeps saved recipes stable if the default
    # ever changes.
    result["traversal"] = condition.traversal
    if condition.include_potential:
        result["include_potential"] = True
    if condition.max_hops is not None:
        result["max_hops"] = condition.max_hops
    return result


def connection_criteria_node_to_mapping(node: object) -> dict[str, Any]:
    if isinstance(node, AttributeCondition):
        return _condition_to_mapping(node)
    if isinstance(node, ConnectionCriteriaGroup):
        return connection_criteria_group_to_mapping(node)
    raise TypeError(f"unrecognized connection criteria node: {node!r}")


def connection_criteria_group_to_mapping(group: ConnectionCriteriaGroup) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "group",
        "conjunction": group.conjunction,
        "children": [connection_criteria_node_to_mapping(c) for c in group.children],
    }
    if group.negate:
        result["negate"] = True
    return result


def neighbor_inclusion_to_mapping(inclusion: NeighborInclusion) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if inclusion.direction != "either":
        result["direction"] = inclusion.direction
    if inclusion.connection_criteria is not None:
        result["connection_criteria"] = connection_criteria_group_to_mapping(inclusion.connection_criteria)
    if inclusion.neighbor_criteria is not None:
        result["neighbor_criteria"] = entity_criteria_group_to_mapping(inclusion.neighbor_criteria)
    if inclusion.traversal != "direct":
        result["traversal"] = inclusion.traversal
    if inclusion.include_potential:
        result["include_potential"] = True
    if inclusion.max_hops is not None:
        result["max_hops"] = inclusion.max_hops
    return result


def connection_selection_to_mapping(selection: ConnectionSelection) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not selection.enabled:
        result["enabled"] = False
    if selection.criteria != ConnectionCriteriaGroup():
        result["criteria"] = connection_criteria_group_to_mapping(selection.criteria)
    if selection.traversal != "direct":
        result["traversal"] = selection.traversal
    if selection.include_potential:
        result["include_potential"] = True
    if selection.max_hops is not None:
        result["max_hops"] = selection.max_hops
    return result
