"""Traversal and type-shape helpers for query declaration validation."""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
)
from src.domain.viewpoints.viewpoint_value_types import (
    EntityInstanceType,
    EntitySetType,
    ListType,
    OptionalType,
    QueryResultType,
)


def binding_references(node: object) -> set[str]:
    return _references(node, "binding")


def parameter_references(node: object) -> set[str]:
    return _references(node, "parameter")


def uses_derived_path(node: object) -> bool:
    if node is None:
        return False
    if isinstance(node, AttributeCondition):
        return node.attribute.startswith("derived.")
    if isinstance(node, (EntityCriteriaGroup, ConnectionCriteriaGroup)):
        return any(uses_derived_path(child) for child in node.children)
    if isinstance(node, IncidentConnectionCondition):
        return uses_derived_path(node.connection_criteria) or uses_derived_path(node.endpoint_criteria)
    return False


def has_cycle(graph: Mapping[str, set[str]]) -> bool:
    active: set[str] = set()
    complete: set[str] = set()

    def visit(name: str) -> bool:
        if name in active:
            return True
        if name in complete:
            return False
        active.add(name)
        result = any(reference in graph and visit(reference) for reference in graph.get(name, set()))
        active.remove(name)
        complete.add(name)
        return result

    return any(visit(name) for name in graph)


def is_entity_value(value: QueryResultType) -> bool:
    if isinstance(value, OptionalType):
        return is_entity_value(value.element)
    if isinstance(value, (EntityInstanceType, EntitySetType)):
        return True
    return isinstance(value, ListType) and isinstance(value.element, EntityInstanceType)


def matches_scalar(value: object, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)


def _references(node: object, kind: str) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, AttributeCondition):
        value = node.value
        if value.kind != kind:
            return set()
        name = value.binding if kind == "binding" else value.parameter
        return {name} if isinstance(name, str) else set()
    if isinstance(node, (EntityCriteriaGroup, ConnectionCriteriaGroup)):
        return set().union(*(_references(child, kind) for child in node.children))
    if isinstance(node, IncidentConnectionCondition):
        return _references(node.connection_criteria, kind) | _references(node.endpoint_criteria, kind)
    return set()
