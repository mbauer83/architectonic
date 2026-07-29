"""Registry-aware validation for viewpoint definitions, with three modes: ``load`` (catalog
load — structural only, registry findings downgraded to warnings),
``save`` (GUI/MCP payload — registry findings become errors, plus authoring-ergonomics
checks), ``persist_edit`` (``save`` plus lifecycle rules against prior state).

Pure and side-effect-free: callers supply the current registries and get back a tuple of
``ViewpointValidationIssue`` — empty means the definition is valid for that mode right now.
Structural correctness (enum values, the query_schema tag) is already enforced by
``viewpoint_parsing.py`` before a definition reaches this module.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_binding_validation import validate_query_values
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue
from src.domain.viewpoints.viewpoint_criteria_validation import (
    validate_connection_selection,
    validate_depth_cap,
    validate_entity_criteria,
    validate_neighbor_inclusion,
)
from src.domain.viewpoints.viewpoint_presentation_validation import validate_presentation
from src.domain.viewpoints.viewpoint_scope_query import classify_selection_layers
from src.domain.viewpoints.viewpoint_trace_pattern_validation import (
    validate_trace_pattern_types,
    validate_trace_patterns,
)
from src.domain.viewpoints.viewpoint_validation_issue import ValidationMode, ViewpointValidationIssue
from src.domain.viewpoints.viewpoint_value_reference_validation import validate_query_value_references
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)

_SEMANTIC_FIELDS = ("scope", "query", "presentation", "representation_types")

_REGISTRY_FINDING_CODES = frozenset(
    {
        "unknown-attribute",
        "unknown-value",
        "unknown-type",
        "operator-type-mismatch",
        "unsupported-capability",
        "unsupported-display-option",
    }
)


def _downgrade_registry_findings(issues: list[ViewpointValidationIssue]) -> tuple[ViewpointValidationIssue, ...]:
    """`load` mode: registry-dependent findings become warnings — a definition that fails a
    registry lookup still loads and degrades loudly at evaluation time. Structural/value-shape
    issues (not in the registry-finding code set) stay errors —
    ergonomics-only codes never appear here since ``check_ergonomics`` is False at load."""
    return tuple(
        ViewpointValidationIssue(
            severity="warning", code=i.code, path=i.path, message=i.message, expected=i.expected, found=i.found
        )
        if i.code in _REGISTRY_FINDING_CODES
        else i
        for i in issues
    )


def _known_domains(registries: RegistrySnapshot) -> frozenset[str]:
    return frozenset(info.hierarchy[0] for info in registries.entity_type_infos.values() if info.hierarchy)


def _validate_scope(scope: ConceptScope, *, path: str, registries: RegistrySnapshot) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if scope.entity_types is not None:
        for unknown in sorted(frozenset(str(t) for t in scope.entity_types) - registries.known_entity_types):
            issues.append(
                issue(
                    "error", "unknown-type", f"{path}/entity_types", f"scope references unknown entity type {unknown!r}"
                )
            )
    if scope.connection_types is not None:
        for unknown in sorted(frozenset(str(t) for t in scope.connection_types) - registries.known_connection_types):
            issues.append(
                issue(
                    "error",
                    "unknown-type",
                    f"{path}/connection_types",
                    f"scope references unknown connection type {unknown!r}",
                )
            )
    for unknown in sorted(frozenset(str(t) for t in scope.excluded_entity_types) - registries.known_entity_types):
        issues.append(
            issue(
                "error",
                "unknown-type",
                f"{path}/excluded_entity_types",
                f"scope references unknown entity type {unknown!r}",
            )
        )
    for unknown in sorted(
        frozenset(str(t) for t in scope.excluded_connection_types) - registries.known_connection_types
    ):
        issues.append(
            issue(
                "error",
                "unknown-type",
                f"{path}/excluded_connection_types",
                f"scope references unknown connection type {unknown!r}",
            )
        )
    excluded_domains = {
        value for predicate in scope.excluded_hierarchy_predicates if predicate.index == 0 for value in predicate.values
    }
    for unknown in sorted(excluded_domains - _known_domains(registries)):
        issues.append(
            issue("error", "unknown-value", f"{path}/excluded_domains", f"scope references unknown domain {unknown!r}")
        )
    return issues


def _validate_query(
    query: ExecutableViewpointQuery,
    *,
    path: str,
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    max_bindings: int,
    max_parameters: int,
    max_derived_attributes: int,
    presentation: PresentationSpec | None,
) -> list[ViewpointValidationIssue]:
    value_issues, value_types = validate_query_values(
        bindings=query.bindings,
        parameters=query.parameters,
        derived=query.derived,
        path=path,
        registries=registries,
        check_ergonomics=check_ergonomics,
        max_bindings=max_bindings,
        max_parameters=max_parameters,
        max_derived_attributes=max_derived_attributes,
    )
    value_issues.extend(
        validate_query_value_references(
            query,
            values=value_types,
            path=path,
            registries=registries,
            presentation=presentation,
        )
    )
    issues = value_issues + validate_entity_criteria(
        query.entity_criteria,
        path=f"{path}/entity_criteria",
        is_root=True,
        registries=registries,
        check_ergonomics=check_ergonomics,
    )
    if check_ergonomics:
        issues.extend(validate_depth_cap(query.entity_criteria, path=f"{path}/entity_criteria", registries=registries))
    for index, inclusion in enumerate(query.include_connected):
        issues.extend(
            validate_neighbor_inclusion(
                inclusion,
                path=f"{path}/include_connected/{index}",
                registries=registries,
                check_ergonomics=check_ergonomics,
            )
        )
    issues.extend(
        validate_connection_selection(
            query.connections, path=f"{path}/connections", registries=registries, check_ergonomics=check_ergonomics
        )
    )
    trace_path = f"{path}/trace_patterns"
    issues.extend(
        validate_trace_patterns(query.trace_patterns, path=trace_path, check_ergonomics=check_ergonomics)
    )
    issues.extend(
        validate_trace_pattern_types(
            query.trace_patterns,
            known_entity_types=registries.known_entity_types,
            known_connection_types=registries.known_connection_types,
            path=trace_path,
        )
    )
    return issues


def _validate_matrix_needs_connections(definition: ViewpointDefinition, *, path: str) -> list[ViewpointValidationIssue]:
    if (
        definition.presentation is None
        or definition.presentation.representation != "matrix"
        or definition.query is None
    ):
        return []
    if not definition.query.connections.enabled:
        return [
            issue(
                "warning",
                "matrix-without-connections",
                f"{path}",
                "a matrix with connections disabled will show empty cells",
            )
        ]
    return []


def _semantic_snapshot(definition: ViewpointDefinition) -> tuple[object, ...]:
    return tuple(getattr(definition, field_name) for field_name in _SEMANTIC_FIELDS)


def _validate_lifecycle(
    definition: ViewpointDefinition, *, prior_definition: ViewpointDefinition | None, catalog: ViewpointCatalog | None
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    if prior_definition is not None and _semantic_snapshot(definition) != _semantic_snapshot(prior_definition):
        if definition.version <= prior_definition.version:
            issues.append(issue("error", "version-not-bumped", "/version", "a semantic edit requires a version bump"))
    if catalog is not None and prior_definition is None and catalog.get(definition.slug) is not None:
        issues.append(
            issue(
                "error",
                "slug-collision",
                "/slug",
                f"a viewpoint named {definition.slug!r} already exists in the merged catalog",
            )
        )
    return issues


def _selection_divergence_issues(definition: ViewpointDefinition) -> list[ViewpointValidationIssue]:
    """INFORMATIONAL only: a divergent inactive layer is the normal state of a definition
    whose author chose one selection mode and kept the other layer for history/conversion.
    Execution and save always follow the active layer; this never blocks either."""
    if classify_selection_layers(definition) != "dual-divergent":
        return []
    active = definition.selection_mode or "query"
    return [
        issue(
            "warning",
            "selection-layers-diverge",
            "/selection_mode",
            f"the scope and query layers select different populations; the {active} layer is active "
            "and the other is informational history",
        )
    ]


def validate_viewpoint_definition(
    definition: ViewpointDefinition,
    *,
    mode: ValidationMode,
    known_entity_types: frozenset[str],
    known_connection_types: frozenset[str],
    known_specialization_slugs: frozenset[str],
    entity_attribute_types: dict[str, str] | None = None,
    connection_attribute_types: dict[str, str] | None = None,
    symmetric_connection_types: frozenset[str] = frozenset(),
    entity_type_infos: Mapping[str, EntityTypeInfo] | None = None,
    depth_cap: int = 4,
    max_query_bindings: int = 8,
    max_query_parameters: int = 4,
    max_derived_attributes: int = 8,
    prior_definition: ViewpointDefinition | None = None,
    catalog: ViewpointCatalog | None = None,
) -> tuple[ViewpointValidationIssue, ...]:
    """Validate one definition against the current registries for the given mode."""
    registries = RegistrySnapshot(
        known_entity_types=known_entity_types,
        known_connection_types=known_connection_types,
        known_specialization_slugs=known_specialization_slugs,
        entity_attribute_types=entity_attribute_types or {},
        connection_attribute_types=connection_attribute_types or {},
        symmetric_connection_types=symmetric_connection_types,
        entity_type_infos=entity_type_infos or {},
        depth_cap=depth_cap,
    )
    check_ergonomics = mode != "load"
    structural_issues = list(_validate_scope(definition.scope, path="/scope", registries=registries))
    structural_issues.extend(_selection_divergence_issues(definition))
    registry_issues: list[ViewpointValidationIssue] = []
    if definition.query is not None:
        registry_issues.extend(
            _validate_query(
                definition.query,
                path="/query",
                registries=registries,
                check_ergonomics=check_ergonomics,
                max_bindings=max_query_bindings,
                max_parameters=max_query_parameters,
                max_derived_attributes=max_derived_attributes,
                presentation=definition.presentation,
            )
        )
    if definition.presentation is not None:
        registry_issues.extend(
            validate_presentation(
                definition.presentation,
                path="/presentation",
                registries=registries,
                check_ergonomics=check_ergonomics,
                declared_derived_names=(
                    frozenset(attribute.name for attribute in definition.query.derived)
                    if definition.query is not None
                    else frozenset()
                ),
            )
        )
        registry_issues.extend(_validate_matrix_needs_connections(definition, path="/presentation"))

    if mode == "load":
        return _downgrade_registry_findings(structural_issues) + _downgrade_registry_findings(registry_issues)

    issues = structural_issues + registry_issues
    if mode == "persist_edit":
        issues = issues + _validate_lifecycle(definition, prior_definition=prior_definition, catalog=catalog)
    return tuple(issues)
