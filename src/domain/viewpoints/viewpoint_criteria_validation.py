"""Registry-aware, recursive validation of criteria trees.

Pure and side-effect-free: callers supply the current registries and get back a tuple
of ``ViewpointValidationIssue``; severities are mode-dependent (``viewpoint_validation.py``
owns the mode dispatch, this module always reasons in "save" terms — the caller downgrades
registry findings to warnings for ``load`` mode). Leaf-condition checks live in
``viewpoint_condition_validation.py``.
"""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue, validate_condition
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    NeighborInclusion,
)
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue

__all__ = [
    "RegistrySnapshot",
    "criteria_tree_depth",
    "validate_connection_criteria",
    "validate_connection_selection",
    "validate_depth_cap",
    "validate_entity_criteria",
    "validate_neighbor_inclusion",
]


def criteria_tree_depth(node: object) -> int:
    """Combined boolean-nesting + relational-hop depth: a group counts one level,
    an incident hop counts one level for the deeper of its two sub-trees."""
    if isinstance(node, (EntityCriteriaGroup, ConnectionCriteriaGroup)):
        return 1 + max((criteria_tree_depth(c) for c in node.children), default=0)
    if isinstance(node, IncidentConnectionCondition):
        sub_depths = [
            criteria_tree_depth(node.connection_criteria) if node.connection_criteria is not None else 0,
            criteria_tree_depth(node.endpoint_criteria) if node.endpoint_criteria is not None else 0,
        ]
        return 1 + max(sub_depths)
    return 0


def validate_depth_cap(node: object, *, path: str, registries: RegistrySnapshot) -> list[ViewpointValidationIssue]:
    depth = criteria_tree_depth(node)
    if depth > registries.depth_cap:
        return [
            issue(
                "error",
                "depth-cap-exceeded",
                path,
                f"criteria tree depth {depth} exceeds the cap of {registries.depth_cap}",
            )
        ]
    return []


def _restricted_to_types(group: ConnectionCriteriaGroup) -> frozenset[str] | None:
    """Best-effort: the set of connection types a top-level conjunctive `type` condition
    restricts to, or None if the tree doesn't obviously restrict to a fixed type set."""
    if group.conjunction != "and":
        return None
    for child in group.children:
        if isinstance(child, AttributeCondition) and child.attribute == "type" and not child.negate:
            if child.comparator == "eq" and isinstance(child.value.literal, str):
                return frozenset({child.value.literal})
            if child.comparator == "in" and isinstance(child.value.literal, (list, tuple)):
                return frozenset(str(v) for v in child.value.literal)
    return None


def _symmetric_direction_warning(
    condition: IncidentConnectionCondition, *, path: str, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    if condition.direction == "either" or condition.connection_criteria is None:
        return []
    restricted = _restricted_to_types(condition.connection_criteria)
    if restricted and restricted <= registries.symmetric_connection_types:
        return [
            issue(
                "warning",
                "symmetric-direction-ineffective",
                f"{path}/direction",
                "direction cannot discriminate when connection_criteria restricts to only symmetric types",
            )
        ]
    return []


def _validate_derived_traversal(
    connection_criteria: ConnectionCriteriaGroup | None, *, traversal: str, max_hops: int | None, path: str
) -> list[ViewpointValidationIssue]:
    if traversal == "direct":
        return []
    issues: list[ViewpointValidationIssue] = []
    if max_hops is not None and max_hops < 2:
        issues.append(
            issue("error", "derivation-hops-exceeded", f"{path}/max_hops", "derived traversal needs at least two hops")
        )
    if connection_criteria is not None:
        issues.extend(_validate_derived_paths(connection_criteria, path=f"{path}/connection_criteria"))
    return issues


def _validate_derived_paths(node: object, *, path: str) -> list[ViewpointValidationIssue]:
    if isinstance(node, AttributeCondition):
        if node.attribute not in {"type", "certainty", "hops"}:
            return [
                issue(
                    "error",
                    "derived-traversal-path-unsupported",
                    path,
                    "derived relationships expose type, certainty, and hops only",
                )
            ]
        if node.value.kind == "attribute_of_endpoint":
            return [
                issue(
                    "error",
                    "derived-traversal-path-unsupported",
                    f"{path}/value",
                    "derived relationships have no endpoint value references",
                )
            ]
        return []
    if isinstance(node, ConnectionCriteriaGroup):
        return [
            issue
            for index, child in enumerate(node.children)
            for issue in _validate_derived_paths(child, path=f"{path}/children/{index}")
        ]
    return []


def validate_entity_criteria(
    node: object, *, path: str, is_root: bool, registries: RegistrySnapshot, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if isinstance(node, AttributeCondition):
        return validate_condition(node, path=path, context="entity", registries=registries)
    if isinstance(node, IncidentConnectionCondition):
        issues.extend(
            _validate_derived_traversal(
                node.connection_criteria, traversal=node.traversal, max_hops=node.max_hops, path=path
            )
        )
        if node.connection_criteria is not None:
            issues.extend(
                validate_connection_criteria(
                    node.connection_criteria,
                    path=f"{path}/connection_criteria",
                    is_root=True,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
            if check_ergonomics:
                issues.extend(_symmetric_direction_warning(node, path=path, registries=registries))
        if node.endpoint_criteria is not None:
            issues.extend(
                validate_entity_criteria(
                    node.endpoint_criteria,
                    path=f"{path}/endpoint_criteria",
                    is_root=True,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
        return issues
    if isinstance(node, EntityCriteriaGroup):
        if check_ergonomics and not is_root and not node.children:
            issues.append(issue("error", "empty-non-root-group", path, "non-root group must have at least one child"))
        for index, child in enumerate(node.children):
            issues.extend(
                validate_entity_criteria(
                    child,
                    path=f"{path}/children/{index}",
                    is_root=False,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
        return issues
    raise TypeError(f"unrecognized entity criteria node: {node!r}")


def validate_connection_criteria(
    node: object, *, path: str, is_root: bool, registries: RegistrySnapshot, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    if isinstance(node, AttributeCondition):
        return validate_condition(node, path=path, context="connection", registries=registries)
    if isinstance(node, ConnectionCriteriaGroup):
        issues: list[ViewpointValidationIssue] = []
        if check_ergonomics and not is_root and not node.children:
            issues.append(issue("error", "empty-non-root-group", path, "non-root group must have at least one child"))
        for index, child in enumerate(node.children):
            issues.extend(
                validate_connection_criteria(
                    child,
                    path=f"{path}/children/{index}",
                    is_root=False,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
        return issues
    raise TypeError(f"unrecognized connection criteria node: {node!r}")


def validate_neighbor_inclusion(
    inclusion: NeighborInclusion, *, path: str, registries: RegistrySnapshot, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    issues.extend(
        _validate_derived_traversal(
            inclusion.connection_criteria, traversal=inclusion.traversal, max_hops=inclusion.max_hops, path=path
        )
    )
    if inclusion.connection_criteria is not None:
        issues.extend(
            validate_connection_criteria(
                inclusion.connection_criteria,
                path=f"{path}/connection_criteria",
                is_root=True,
                registries=registries,
                check_ergonomics=check_ergonomics,
            )
        )
        if check_ergonomics:
            issues.extend(
                validate_depth_cap(
                    inclusion.connection_criteria, path=f"{path}/connection_criteria", registries=registries
                )
            )
    if inclusion.neighbor_criteria is not None:
        issues.extend(
            validate_entity_criteria(
                inclusion.neighbor_criteria,
                path=f"{path}/neighbor_criteria",
                is_root=True,
                registries=registries,
                check_ergonomics=check_ergonomics,
            )
        )
        if check_ergonomics:
            issues.extend(
                validate_depth_cap(inclusion.neighbor_criteria, path=f"{path}/neighbor_criteria", registries=registries)
            )
    return issues


def validate_connection_selection(
    selection: ConnectionSelection, *, path: str, registries: RegistrySnapshot, check_ergonomics: bool
) -> list[ViewpointValidationIssue]:
    if selection.traversal != "direct":
        issues = _validate_derived_paths(selection.criteria, path=f"{path}/criteria")
        if selection.max_hops is not None and selection.max_hops < 2:
            issues.append(
                issue(
                    "error",
                    "derivation-hops-exceeded",
                    f"{path}/max_hops",
                    "derived traversal needs at least two hops",
                )
            )
        return issues
    issues = validate_connection_criteria(
        selection.criteria,
        path=f"{path}/criteria",
        is_root=True,
        registries=registries,
        check_ergonomics=check_ergonomics,
    )
    if check_ergonomics:
        issues.extend(validate_depth_cap(selection.criteria, path=f"{path}/criteria", registries=registries))
    return issues
