"""Type-check binding and parameter references used by query criteria."""

from __future__ import annotations

from typing import cast

from src.domain.viewpoints.viewpoint_binding_validation import QueryValueTypes
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue, resolve_attribute_path
from src.domain.viewpoints.viewpoint_criteria import (
    STRING_LIKE_ATTRIBUTE_TYPES,
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    ValueRef,
    scalar_kinds_comparable,
)
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoint_value_types import (
    ListType,
    QueryResultType,
    ScalarKind,
    ScalarType,
    TupleType,
    infer_binding_type,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec


def validate_query_value_references(
    query: ExecutableViewpointQuery,
    *,
    values: QueryValueTypes,
    path: str,
    registries: RegistrySnapshot,
    presentation: PresentationSpec | None = None,
) -> list[ViewpointValidationIssue]:
    issues = _validate_entity_tree(query.entity_criteria, f"{path}/entity_criteria", values, registries)
    for index, binding in enumerate(query.bindings):
        issues.extend(
            _validate_binding_criteria(binding.criteria, f"{path}/bindings/{index}/criteria", values, registries)
        )
    for index, attribute in enumerate(query.derived):
        issues.extend(
            _validate_connection_tree(
                attribute.connection_criteria,
                f"{path}/derived/{index}/connection_criteria",
                values,
                registries,
            )
        )
        issues.extend(
            _validate_entity_tree(
                attribute.endpoint_criteria,
                f"{path}/derived/{index}/endpoint_criteria",
                values,
                registries,
            )
        )
    for index, inclusion in enumerate(query.include_connected):
        issues.extend(
            _validate_connection_tree(
                inclusion.connection_criteria,
                f"{path}/include_connected/{index}/connection_criteria",
                values,
                registries,
            )
        )
        issues.extend(
            _validate_entity_tree(
                inclusion.neighbor_criteria,
                f"{path}/include_connected/{index}/neighbor_criteria",
                values,
                registries,
            )
        )
    issues.extend(
        _validate_connection_tree(query.connections.criteria, f"{path}/connections/criteria", values, registries)
    )
    if presentation is not None:
        issues.extend(_validate_presentation(presentation, "/presentation", values, registries))
    return issues


def _validate_presentation(
    presentation: PresentationSpec,
    path: str,
    values: QueryValueTypes,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    issues = _validate_entity_tree(presentation.row_criteria, f"{path}/row_criteria", values, registries)
    issues.extend(_validate_entity_tree(presentation.column_criteria, f"{path}/column_criteria", values, registries))
    for index, rule in enumerate(presentation.styling_rules):
        rule_path = f"{path}/styling_rules/{index}/match_criteria"
        if isinstance(rule.match_criteria, EntityCriteriaGroup):
            issues.extend(_validate_entity_tree(rule.match_criteria, rule_path, values, registries))
        elif isinstance(rule.match_criteria, ConnectionCriteriaGroup):
            issues.extend(_validate_connection_tree(rule.match_criteria, rule_path, values, registries))
    return issues


def _validate_binding_criteria(
    criteria: EntityCriteriaGroup | ConnectionCriteriaGroup | None,
    path: str,
    values: QueryValueTypes,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    if isinstance(criteria, EntityCriteriaGroup):
        return _validate_entity_tree(criteria, path, values, registries)
    if isinstance(criteria, ConnectionCriteriaGroup):
        return _validate_connection_tree(criteria, path, values, registries)
    return []


def _validate_entity_tree(
    node: object,
    path: str,
    values: QueryValueTypes,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    if node is None:
        return []
    if isinstance(node, AttributeCondition):
        return _validate_reference(node, path, "entity", values, registries)
    if isinstance(node, EntityCriteriaGroup):
        return [
            issue_item
            for index, child in enumerate(node.children)
            for issue_item in _validate_entity_tree(child, f"{path}/children/{index}", values, registries)
        ]
    if isinstance(node, IncidentConnectionCondition):
        return _validate_connection_tree(
            node.connection_criteria, f"{path}/connection_criteria", values, registries
        ) + _validate_entity_tree(node.endpoint_criteria, f"{path}/endpoint_criteria", values, registries)
    return []


def _validate_connection_tree(
    node: object,
    path: str,
    values: QueryValueTypes,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    if node is None:
        return []
    if isinstance(node, AttributeCondition):
        return _validate_reference(node, path, "connection", values, registries)
    if isinstance(node, ConnectionCriteriaGroup):
        return [
            issue_item
            for index, child in enumerate(node.children)
            for issue_item in _validate_connection_tree(child, f"{path}/children/{index}", values, registries)
        ]
    return []


def _validate_reference(
    condition: AttributeCondition,
    path: str,
    context: str,
    values: QueryValueTypes,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    if condition.attribute.startswith("derived."):
        name = condition.attribute.removeprefix("derived.")
        if name not in values.derived:
            return [
                issue(
                    "error",
                    "derived-attribute-unknown",
                    f"{path}/attribute",
                    "unknown derived attribute",
                    expected="a declared derived attribute",
                    found=name,
                )
            ]
    value = condition.value
    if value.kind == "binding":
        reference_type = values.bindings.get(value.binding or "")
        if reference_type is None:
            return [
                issue("error", "unknown-binding", f"{path}/value", "unknown binding reference", found=value.binding)
            ]
        return _validate_binding_reference(condition, value, reference_type, path, context, registries)
    if value.kind == "parameter":
        parameter = values.parameters.get(value.parameter or "")
        if parameter is None:
            return [
                issue(
                    "error", "unknown-parameter", f"{path}/value", "unknown parameter reference", found=value.parameter
                )
            ]
        # A set-valued parameter resolves to an ordered tuple, so its reference type is a LIST
        # of its element kind — that is what makes it a legal operand of the existing `in`
        # comparator (the binding set-valued parameters exist for). Scalars stay scalar;
        # entity-id compares as its string id.
        kind = parameter.value_type
        element = ScalarType(cast(ScalarKind, "string" if kind == "entity-id" else kind))
        parameter_type: QueryResultType = ListType(element) if parameter.is_set_valued else element
        return _validate_reference_type(condition, parameter_type, value, path, context, registries)
    return []


def _validate_binding_reference(
    condition: AttributeCondition,
    value: ValueRef,
    reference_type: QueryResultType,
    path: str,
    context: str,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    try:
        resolved = infer_binding_type(
            input_type=reference_type,
            project=value.project,
            aggregate=value.aggregate,
            registries=registries,
        )
    except ValueError as error:
        return [issue("error", getattr(error, "code", "binding-type-mismatch"), f"{path}/value", str(error))]
    return _validate_reference_type(condition, resolved, value, path, context, registries)


def _validate_reference_type(
    condition: AttributeCondition,
    reference_type: QueryResultType,
    value: ValueRef,
    path: str,
    context: str,
    registries: RegistrySnapshot,
) -> list[ViewpointValidationIssue]:
    if context == "entity":
        left = resolve_attribute_path(condition.attribute, context="entity", registries=registries)
    else:
        left = resolve_attribute_path(condition.attribute, context="connection", registries=registries)
    if left is None:
        return []
    left_kind = "string" if left == "reserved" else left
    # Tracked separately from `reference_type` because the list branch below unwraps a
    # `ListType` down to its scalar element for the rest of this function's checks — losing
    # that flag would make every `in`/`not_in` reference look scalar by the time the
    # "requires a list reference" check runs, rejecting the exact list references it exists
    # to accept.
    was_list = False
    if isinstance(reference_type, ListType):
        was_list = True
        if value.quantifier is None and condition.comparator not in ("in", "not_in"):
            return [
                issue(
                    "error",
                    "unquantified-set-comparison",
                    f"{path}/value",
                    "a list reference needs an aggregate or quantifier",
                    expected="aggregate or quantifier",
                    found="list",
                )
            ]
        if not isinstance(reference_type.element, ScalarType):
            return [issue("error", "operator-type-mismatch", f"{path}/value", "list elements must be scalar")]
        reference_type = reference_type.element
    if isinstance(reference_type, TupleType):
        if condition.comparator not in {"eq", "in", "not_in"}:
            return [
                issue(
                    "error",
                    "tuple-comparator-unsupported",
                    f"{path}/comparator",
                    "tuple values support eq, in, or not_in only",
                )
            ]
        return []
    if not isinstance(reference_type, ScalarType):
        return [issue("error", "operator-type-mismatch", f"{path}/value", "reference is not scalar")]
    if condition.comparator in ("in", "not_in") and not was_list:
        message = f"{condition.comparator} requires a list reference"
        return [issue("error", "operator-type-mismatch", f"{path}/comparator", message)]
    if condition.comparator in ("like", "ilike") and reference_type.kind not in STRING_LIKE_ATTRIBUTE_TYPES:
        return [
            issue(
                "error",
                "operator-type-mismatch",
                f"{path}/value",
                f"{condition.comparator} requires a string reference",
                expected="string",
                found=reference_type.kind,
            )
        ]
    if not scalar_kinds_comparable(reference_type.kind, left_kind):
        return [
            issue(
                "error",
                "operator-type-mismatch",
                f"{path}/value",
                "reference type differs from the compared attribute",
                expected=left_kind,
                found=reference_type.kind,
            )
        ]
    return []
