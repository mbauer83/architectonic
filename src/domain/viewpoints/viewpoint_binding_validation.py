"""Static validation of query binding, parameter, and derived-attribute declarations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.viewpoints.viewpoint_binding_validation_helpers import (
    binding_references,
    has_cycle,
    is_entity_value,
    matches_scalar,
    parameter_references,
    uses_derived_path,
)
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding, QueryParameter
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue, resolve_attribute_path
from src.domain.viewpoints.viewpoint_set_parameters import set_parameter_issues
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoint_value_types import (
    QueryResultType,
    assert_types_are_compatible,
    infer_binding_type,
)


@dataclass(frozen=True)
class QueryValueTypes:
    bindings: Mapping[str, QueryResultType]
    # The full declaration, not just its type name: a reference's legal comparators depend on
    # CARDINALITY as well as element kind (a set-valued parameter is a legal `in` operand).
    parameters: Mapping[str, QueryParameter]
    derived: Mapping[str, str]


def validate_query_values(
    *,
    bindings: tuple[QueryBinding, ...],
    parameters: tuple[QueryParameter, ...],
    derived: tuple[DerivedAttribute, ...],
    path: str,
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    max_bindings: int,
    max_parameters: int,
    max_derived_attributes: int,
) -> tuple[list[ViewpointValidationIssue], QueryValueTypes]:
    issues = _validate_parameters(
        parameters,
        path=f"{path}/parameters",
        check_ergonomics=check_ergonomics,
        cap=max_parameters,
    )
    parameter_types = {parameter.name: parameter for parameter in parameters}
    binding_issues, binding_types = _validate_bindings(
        bindings,
        path=f"{path}/bindings",
        registries=registries,
        check_ergonomics=check_ergonomics,
        cap=max_bindings,
        parameter_types=parameter_types,
    )
    issues.extend(binding_issues)
    derived_issues, derived_types = _validate_derived(
        derived,
        path=f"{path}/derived",
        registries=registries,
        check_ergonomics=check_ergonomics,
        cap=max_derived_attributes,
        binding_types=binding_types,
        parameter_types=parameter_types,
    )
    issues.extend(derived_issues)
    return issues, QueryValueTypes(bindings=binding_types, parameters=parameter_types, derived=derived_types)


def _validate_parameters(
    parameters: tuple[QueryParameter, ...], *, path: str, check_ergonomics: bool, cap: int
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    seen: set[str] = set()
    for index, parameter in enumerate(parameters):
        item_path = f"{path}/{index}"
        if parameter.name in seen:
            issues.append(
                issue("error", "duplicate-parameter-name", f"{item_path}/name", "parameter name must be unique")
            )
        seen.add(parameter.name)
        if parameter.is_set_valued:
            issues.extend(set_parameter_issues(parameter, item_path))
        elif parameter.default is not None and not matches_scalar(parameter.default, parameter.value_type):
            issues.append(
                issue(
                    "error",
                    "parameter-type-mismatch",
                    f"{item_path}/default",
                    "parameter default does not match its declared type",
                    expected=parameter.value_type,
                    found=type(parameter.default).__name__,
                )
            )
    if check_ergonomics and len(parameters) > cap:
        issues.append(
            issue(
                "error",
                "parameter-count-exceeded",
                path,
                f"at most {cap} parameters are allowed",
                expected=str(cap),
                found=str(len(parameters)),
            )
        )
    return issues


def _validate_bindings(
    bindings: tuple[QueryBinding, ...],
    *,
    path: str,
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    cap: int,
    parameter_types: Mapping[str, QueryParameter],
) -> tuple[list[ViewpointValidationIssue], dict[str, QueryResultType]]:
    issues: list[ViewpointValidationIssue] = []
    declared = {binding.name: binding.result_type for binding in bindings}
    available: dict[str, QueryResultType] = {}
    seen: set[str] = set()
    dependencies: dict[str, set[str]] = {}
    for index, binding in enumerate(bindings):
        item_path = f"{path}/{index}"
        if binding.name in seen:
            issues.append(issue("error", "duplicate-binding-name", f"{item_path}/name", "binding name must be unique"))
        seen.add(binding.name)
        refs = binding_references(binding.criteria)
        dependencies[binding.name] = refs
        for name in refs:
            if name not in declared or name not in available:
                issues.append(
                    issue(
                        "error",
                        "unknown-binding",
                        f"{item_path}/criteria",
                        f"binding {name!r} is unavailable",
                        expected="an earlier binding",
                        found=name,
                    )
                )
        for name in parameter_references(binding.criteria):
            if name not in parameter_types:
                issues.append(
                    issue(
                        "error", "unknown-parameter", f"{item_path}/criteria", f"unknown parameter {name!r}", found=name
                    )
                )
        if uses_derived_path(binding.criteria):
            issues.append(
                issue(
                    "error",
                    "binding-derived-reference-unsupported",
                    f"{item_path}/criteria",
                    "bindings cannot reference derived attributes",
                )
            )
        tuple_types = tuple(available[name] for name in binding.tuple_of if name in available)
        for name in binding.tuple_of:
            if name not in available:
                issues.append(
                    issue(
                        "error",
                        "unknown-binding",
                        f"{item_path}/tuple",
                        f"binding {name!r} is unavailable",
                        expected="an earlier binding",
                        found=name,
                    )
                )
        try:
            inferred = infer_binding_type(
                select=binding.select,
                criteria=binding.criteria,
                project=binding.project,
                aggregate=binding.aggregate,
                tuple_elements=tuple_types,
                registries=registries,
            )
            assert_types_are_compatible(binding.result_type, inferred)
        except ValueError as error:
            code = getattr(error, "code", "binding-type-mismatch")
            issues.append(
                issue(
                    "error",
                    code,
                    f"{item_path}/result_type",
                    str(error),
                    expected="compatible inferred type",
                    found=str(binding.result_type),
                )
            )
        if binding.include_in_result and not is_entity_value(binding.result_type):
            issues.append(
                issue(
                    "error",
                    "include-in-result-shape-unsupported",
                    f"{item_path}/include_in_result",
                    "only entity-valued bindings may widen the result",
                )
            )
        available.setdefault(binding.name, binding.result_type)
    if has_cycle(dependencies):
        issues.append(issue("error", "binding-cycle", path, "binding references contain a cycle"))
    if check_ergonomics and len(bindings) > cap:
        issues.append(
            issue(
                "error",
                "binding-count-exceeded",
                path,
                f"at most {cap} bindings are allowed",
                expected=str(cap),
                found=str(len(bindings)),
            )
        )
    return issues, available


def _validate_derived(
    derived: tuple[DerivedAttribute, ...],
    *,
    path: str,
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    cap: int,
    binding_types: Mapping[str, QueryResultType],
    parameter_types: Mapping[str, QueryParameter],
) -> tuple[list[ViewpointValidationIssue], dict[str, str]]:
    issues: list[ViewpointValidationIssue] = []
    types: dict[str, str] = {}
    seen: set[str] = set()
    for index, attribute in enumerate(derived):
        item_path = f"{path}/{index}"
        if attribute.name in seen:
            issues.append(
                issue(
                    "error",
                    "derived-attribute-unknown",
                    f"{item_path}/name",
                    "derived attribute name must be unique",
                )
            )
        seen.add(attribute.name)
        if attribute.source == "security-signal":
            # Externally fetched metric: no graph fields to validate (the parser
            # already rejects them); values are numeric for scale styling.
            types[attribute.name] = "number"
            continue
        if attribute.reduce == "count":
            if attribute.of is not None:
                issues.append(
                    issue(
                        "error",
                        "derived-reduce-type-mismatch",
                        f"{item_path}/of",
                        "count does not take an attribute source",
                    )
                )
            types[attribute.name] = "integer"
        elif attribute.of is None:
            issues.append(
                issue(
                    "error",
                    "derived-of-missing",
                    f"{item_path}/of",
                    "a non-count reduction needs an attribute source",
                )
            )
        else:
            if attribute.of == "relationship.hops" and attribute.traversal != "derived":
                issues.append(
                    issue(
                        "error",
                        "derived-of-source-traversal-mismatch",
                        f"{item_path}/of",
                        "relationship.hops requires relationship-derived traversal",
                    )
                )
            source_type = _derived_source_type(attribute, registries)
            if source_type is None:
                issues.append(
                    issue(
                        "error",
                        "derived-reduce-type-mismatch",
                        f"{item_path}/of",
                        "derived source cannot be reduced",
                        found=attribute.of,
                    )
                )
            else:
                types[attribute.name] = source_type
        binding_refs = binding_references(attribute.connection_criteria) | binding_references(
            attribute.endpoint_criteria
        )
        for name in binding_refs:
            if name not in binding_types:
                issues.append(
                    issue(
                        "error",
                        "unknown-binding",
                        f"{item_path}/connection_criteria",
                        f"unknown binding {name!r}",
                        found=name,
                    )
                )
        parameter_refs = parameter_references(attribute.connection_criteria) | parameter_references(
            attribute.endpoint_criteria
        )
        for name in parameter_refs:
            if name not in parameter_types:
                issues.append(
                    issue(
                        "error",
                        "unknown-parameter",
                        f"{item_path}/connection_criteria",
                        f"unknown parameter {name!r}",
                        found=name,
                    )
                )
        if uses_derived_path(attribute.connection_criteria) or uses_derived_path(attribute.endpoint_criteria):
            issues.append(
                issue(
                    "error",
                    "derived-attribute-reference-unsupported",
                    item_path,
                    "derived attributes cannot reference other derived attributes",
                )
            )
    if check_ergonomics and len(derived) > cap:
        issues.append(
            issue(
                "error",
                "derived-attribute-count-exceeded",
                path,
                f"at most {cap} derived attributes are allowed",
                expected=str(cap),
                found=str(len(derived)),
            )
        )
    return issues, types


def _derived_source_type(attribute: DerivedAttribute, registries: RegistrySnapshot) -> str | None:
    if attribute.of == "relationship.hops":
        return "integer" if attribute.traversal == "derived" else None
    if attribute.of is None or "." not in attribute.of:
        return None
    source, name = attribute.of.split(".", 1)
    if source == "connection":
        resolved = resolve_attribute_path(name, context="connection", registries=registries)
    elif source == "endpoint":
        resolved = resolve_attribute_path(name, context="entity", registries=registries)
    else:
        return None
    if resolved in {None, "reserved"}:
        return "string" if resolved == "reserved" else None
    if attribute.reduce in {"sum", "avg"} and resolved not in {"integer", "number"}:
        return None
    if attribute.reduce in {"min", "max"} and resolved not in {"integer", "number", "date"}:
        return None
    return "number" if attribute.reduce == "avg" else resolved
