"""Leaf-level validation for one ``AttributeCondition``: value shape per comparator,
attribute resolution (reserved path vs. effective schema), and
comparator/type gating. Split out of ``viewpoint_criteria_validation.py`` to keep tree
recursion and leaf checks each independently readable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND, ordinal_scales_match
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_criteria import (
    NUMERIC_OPERATORS,
    ORDERED_ATTRIBUTE_TYPES,
    RESERVED_CONNECTION_PATHS,
    RESERVED_ENTITY_PATHS,
    STRING_ATTRIBUTE_TYPES,
    STRING_PATTERN_OPERATORS,
    AttributeCondition,
)
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue

CriteriaContext = Literal["entity", "connection"]

_DECLARATION_CODES = frozenset(
    {
        "unknown-binding",
        "binding-cycle",
        "duplicate-binding-name",
        "binding-type-mismatch",
        "binding-attribute-type-ambiguous",
        "binding-count-exceeded",
        "binding-derived-reference-unsupported",
        "aggregate-over-instance",
        "include-in-result-shape-unsupported",
        "unquantified-set-comparison",
        "tuple-comparator-unsupported",
        "unknown-parameter",
        "duplicate-parameter-name",
        "parameter-type-mismatch",
        "parameter-count-exceeded",
        "derived-attribute-unknown",
        "derived-attribute-count-exceeded",
        "derived-attribute-reference-unsupported",
        "derived-of-missing",
        "derived-reduce-type-mismatch",
        "derived-of-source-traversal-mismatch",
    }
)


@dataclass(frozen=True)
class RegistrySnapshot:
    """Everything criteria-tree validation needs to resolve against the current
    repository/registries — bundled to keep recursive call signatures manageable."""

    known_entity_types: frozenset[str]
    known_connection_types: frozenset[str]
    known_specialization_slugs: frozenset[str]
    entity_attribute_types: Mapping[str, str]
    connection_attribute_types: Mapping[str, str]
    # Enumerable value sets for schema attributes that declare a JSON-schema ``enum`` —
    # keyed by the same flat attribute-path namespace as ``*_attribute_types``. Feeds the
    # criteria-builder's value picker (a dropdown instead of free text); validation ignores
    # it, so an existing value outside the set is never retroactively rejected.
    entity_attribute_enums: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    connection_attribute_enums: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    symmetric_connection_types: frozenset[str] = frozenset()
    entity_type_infos: Mapping[str, EntityTypeInfo] = field(default_factory=dict)
    depth_cap: int = 4
    derivation_catalog: ModuleCatalog | None = None
    derivation_max_hops: int = 4
    derivation_max_relationships: int = 2000
    derivation_time_budget_seconds: float = 2.0


def issue(
    severity: Literal["error", "warning"],
    code: str,
    path: str,
    message: str,
    *,
    expected: str | None = None,
    found: str | None = None,
) -> ViewpointValidationIssue:
    if code in _DECLARATION_CODES:
        expected = expected or "valid declaration"
        found = found or "invalid declaration"
    return ViewpointValidationIssue(
        severity=severity,
        code=code,
        path=path,
        message=message,
        expected=expected,
        found=found,
    )


def resolve_attribute_path(
    attribute: str, *, context: CriteriaContext, registries: RegistrySnapshot
) -> str | Literal["reserved"] | None:
    """Resolve a dotted attribute path's declared type: ``"reserved"`` for a reserved path,
    the declared schema type string for a known profile attribute, or ``None`` if
    unknown against both."""
    head = attribute.split(".", 1)[0]
    reserved = RESERVED_ENTITY_PATHS if context == "entity" else RESERVED_CONNECTION_PATHS
    if head in reserved:
        return "reserved"
    attribute_types = (
        registries.entity_attribute_types if context == "entity" else registries.connection_attribute_types
    )
    return attribute_types.get(attribute)


def _validate_value_shape(
    condition: AttributeCondition, *, path: str, context: CriteriaContext
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    value = condition.value
    if condition.comparator in ("exists", "absent"):
        if value.kind != "literal" or value.literal is not None:
            issues.append(issue("error", "unexpected-value", f"{path}/value", f"{condition.comparator} takes no value"))
        return issues
    if value.kind == "attribute_of_endpoint":
        if value.endpoint is None:
            issues.append(
                issue("error", "value-ref-missing-endpoint", f"{path}/value", "attribute_of_endpoint requires endpoint")
            )
        if context != "connection":
            issues.append(
                issue(
                    "error",
                    "value-ref-endpoint-outside-connection",
                    f"{path}/value",
                    "attribute_of_endpoint is only valid within a connection condition",
                )
            )
    if value.kind in ("attribute_of_self", "attribute_of_endpoint") and not value.attribute:
        issues.append(
            issue("error", "value-ref-missing-attribute", f"{path}/value", f"{value.kind} requires attribute")
        )
    is_list_comparator = condition.comparator in ("in", "not_in")
    if is_list_comparator and value.kind == "literal" and not isinstance(value.literal, (list, tuple)):
        message = f"{condition.comparator!r} requires a list value"
        issues.append(issue("error", "unsupported-value-shape", f"{path}/value", message))
    is_pattern_comparator = condition.comparator in STRING_PATTERN_OPERATORS
    if is_pattern_comparator and value.kind == "literal" and not isinstance(value.literal, str):
        message = f"{condition.comparator!r} requires a string pattern value"
        issues.append(issue("error", "unsupported-value-shape", f"{path}/value", message))
    return issues


def _validate_reserved_value(
    condition: AttributeCondition, *, path: str, context: CriteriaContext, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    if condition.value.kind != "literal" or condition.comparator not in ("eq", "neq", "in", "not_in"):
        return []
    head = condition.attribute.split(".", 1)[0]
    values = (
        condition.value.literal if isinstance(condition.value.literal, (list, tuple)) else [condition.value.literal]
    )
    known: frozenset[str] | None = None
    if head == "type":
        known = registries.known_entity_types if context == "entity" else registries.known_connection_types
    elif head == "specialization":
        known = registries.known_specialization_slugs
    if known is None:
        return []
    return [
        issue("error", "unknown-value", f"{path}/value", f"{head} value {value!r} is not a known slug")
        for value in values
        if isinstance(value, str) and value not in known
    ]


def attribute_ordinal_scale(
    attribute: str, *, context: CriteriaContext, registries: RegistrySnapshot
) -> tuple[str, ...] | None:
    """The ranked member list of an ordinal attribute, or None if it is not one.

    The enum already recorded for the value picker is the scale: an ordinal declares that the
    same members are written in ascending rank order, so there is no second list to keep.
    """
    if resolve_attribute_path(attribute, context=context, registries=registries) != ORDINAL_KIND:
        return None
    enums = registries.entity_attribute_enums if context == "entity" else registries.connection_attribute_enums
    declared = enums.get(attribute)
    return tuple(declared) if declared else None


def _validate_ordinal_comparison(
    condition: AttributeCondition, *, path: str, context: CriteriaContext, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    """Reject ranking an ordinal against a different scale, or against no scale at all.

    Ranks are positions within one enum. Comparing across two enums compares positions that
    count different things, which yields an answer with no meaning rather than an error at
    runtime — so it is refused while the query is being saved.
    """
    if condition.comparator not in NUMERIC_OPERATORS:
        return []
    scale = attribute_ordinal_scale(condition.attribute, context=context, registries=registries)
    if scale is None:
        return [issue(
            "error",
            "ordinal-scale-missing",
            f"{path}/attribute",
            f"attribute {condition.attribute!r} is declared ordinal but no ranked value list "
            "was found for it, so it cannot be ordered",
        )]
    if condition.value.kind not in ("attribute_of_self", "attribute_of_endpoint"):
        return []
    other = condition.value.attribute or ""
    other_context: CriteriaContext = "entity" if condition.value.kind == "attribute_of_endpoint" else context
    other_scale = attribute_ordinal_scale(other, context=other_context, registries=registries)
    if ordinal_scales_match(scale, other_scale):
        return []
    return [issue(
        "error",
        "ordinal-scale-mismatch",
        f"{path}/value",
        f"cannot order {condition.attribute!r} against {other!r}: their ranks are positions in "
        "different value lists, so comparing them compares unlike scales",
    )]


def validate_condition(
    condition: AttributeCondition, *, path: str, context: CriteriaContext, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    issues = _validate_value_shape(condition, path=path, context=context)
    declared = resolve_attribute_path(condition.attribute, context=context, registries=registries)
    if declared is None:
        issues.append(
            issue("error", "unknown-attribute", f"{path}/attribute", f"unknown attribute {condition.attribute!r}")
        )
        return issues
    if declared == "reserved":
        if condition.comparator in NUMERIC_OPERATORS:
            message = (
                f"numeric comparator {condition.comparator!r} is not valid for reserved path {condition.attribute!r}"
            )
            issues.append(issue("error", "operator-type-mismatch", f"{path}/comparator", message))
        issues.extend(_validate_reserved_value(condition, path=path, context=context, registries=registries))
        return issues
    if condition.comparator in NUMERIC_OPERATORS and declared not in ORDERED_ATTRIBUTE_TYPES:
        comparator, attribute = condition.comparator, condition.attribute
        message = f"comparator {comparator!r} invalid for attribute {attribute!r} of type {declared!r}"
        issues.append(issue("error", "operator-type-mismatch", f"{path}/comparator", message))
    if declared == ORDINAL_KIND:
        issues.extend(_validate_ordinal_comparison(condition, path=path, context=context, registries=registries))
    if condition.comparator in STRING_PATTERN_OPERATORS and declared not in STRING_ATTRIBUTE_TYPES:
        comparator, attribute = condition.comparator, condition.attribute
        message = f"comparator {comparator!r} invalid for attribute {attribute!r} of type {declared!r}"
        issues.append(issue("error", "operator-type-mismatch", f"{path}/comparator", message))
    return issues
