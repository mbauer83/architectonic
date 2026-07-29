"""Registry-aware validation of a ``PresentationSpec``: capability
agreement per representation, style-rule mode shape (match vs. range), range-band overlap,
matrix axis-mode exclusivity, and column/group_by attribute resolution.
"""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_aggregation import AGGREGATION_DIMENSIONS
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue, resolve_attribute_path
from src.domain.viewpoints.viewpoint_criteria_validation import (
    validate_depth_cap,
    validate_entity_criteria,
)
from src.domain.viewpoints.viewpoint_display_option_validation import (
    COLOR_BY_OPTION,
    LABEL_ATTRIBUTE_OPTION,
    LAYOUT_OPTION,
    validate_color_by_option,
    validate_label_attribute,
    validate_layout_option,
)
from src.domain.viewpoints.viewpoint_style_rule_validation import style_value_issues, validate_style_rule
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoints import (
    GROUP_BY_DIMENSIONS,
    REPRESENTATION_CAPABILITIES,
    PresentationSpec,
)


def _validate_group_by_field(
    value: str | None, *, path: str, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    if value is None or value in GROUP_BY_DIMENSIONS:
        return []
    declared = resolve_attribute_path(value, context="entity", registries=registries)
    if declared is None:
        return [issue("error", "unknown-attribute", path, f"unknown group-by attribute {value!r}")]
    return []







def validate_presentation(
    presentation: PresentationSpec,
    *,
    path: str,
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    declared_derived_names: frozenset[str] = frozenset(),
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    capabilities = REPRESENTATION_CAPABILITIES[presentation.representation]
    for option in presentation.display_options:
        if option in (LABEL_ATTRIBUTE_OPTION, LAYOUT_OPTION, COLOR_BY_OPTION):
            continue
        if option not in capabilities:
            issues.append(
                issue(
                    "error",
                    "unsupported-display-option",
                    f"{path}/display_options/{option}",
                    f"display option {option!r} is unsupported by representation {presentation.representation!r}",
                )
            )
    issues.extend(validate_label_attribute(presentation, path=path, registries=registries))
    issues.extend(validate_layout_option(presentation, path=path))
    issues.extend(validate_color_by_option(presentation, path=path))
    for key, token in presentation.default_style.items():
        if key not in capabilities:
            issues.append(
                issue(
                    "error",
                    "unsupported-capability",
                    f"{path}/default_style/{key}",
                    f"capability {key!r} is unsupported by representation {presentation.representation!r}",
                )
            )
        issues.extend(style_value_issues(key, ((f"{path}/default_style/{key}", token),)))
    for index, rule in enumerate(presentation.styling_rules):
        issues.extend(
            validate_style_rule(
                rule,
                path=f"{path}/styling_rules/{index}",
                representation_capabilities=capabilities,
                registries=registries,
                check_ergonomics=check_ergonomics,
                declared_derived_names=declared_derived_names,
            )
        )
    if presentation.columns is not None:
        for index, column in enumerate(presentation.columns):
            declared = resolve_attribute_path(column.source, context="entity", registries=registries)
            if declared is None:
                issues.append(
                    issue(
                        "error",
                        "unknown-attribute",
                        f"{path}/columns/{index}/source",
                        f"unknown column source {column.source!r}",
                    )
                )
    if presentation.target_types is not None:
        for index, type_name in enumerate(presentation.target_types):
            if type_name not in registries.known_entity_types:
                issues.append(
                    issue(
                        "error",
                        "unknown-entity-type",
                        f"{path}/target_types/{index}",
                        f"unknown target entity type {type_name!r}",
                    )
                )
    issues.extend(_validate_group_by_field(presentation.group_by, path=f"{path}/group_by", registries=registries))
    if presentation.legibility_budget is not None and presentation.legibility_budget < 1:
        issues.append(
            issue(
                "error",
                "invalid-legibility-budget",
                f"{path}/legibility_budget",
                "legibility_budget must be a positive node count",
            )
        )
    if presentation.aggregate_by is not None and presentation.aggregate_by not in AGGREGATION_DIMENSIONS:
        issues.append(
            issue(
                "error",
                "invalid-aggregation-dimension",
                f"{path}/aggregate_by",
                f"aggregate_by must be one of {sorted(AGGREGATION_DIMENSIONS)}",
            )
        )
    if check_ergonomics:
        issues.extend(_validate_matrix_axes(presentation, path=path, registries=registries))
    return issues


def _validate_matrix_axes(
    presentation: PresentationSpec, *, path: str, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    grouped = presentation.row_by is not None or presentation.column_by is not None
    criteria_axes = presentation.row_criteria is not None or presentation.column_criteria is not None
    if grouped and criteria_axes:
        issues.append(issue("error", "matrix-axis-mode-mixed", path, "matrix cannot mix grouped and criteria axes"))
        return issues
    if grouped and (presentation.row_by is None) != (presentation.column_by is None):
        issues.append(
            issue("error", "matrix-axis-incomplete", path, "grouped matrix axes require both row_by and column_by")
        )
    if criteria_axes and (presentation.row_criteria is None) != (presentation.column_criteria is None):
        issues.append(
            issue(
                "error",
                "matrix-axis-incomplete",
                path,
                "criteria matrix axes require both row_criteria and column_criteria",
            )
        )
    for field_name, tree in (("row_by", presentation.row_by), ("column_by", presentation.column_by)):
        issues.extend(_validate_group_by_field(tree, path=f"{path}/{field_name}", registries=registries))
    for field_name, group in (
        ("row_criteria", presentation.row_criteria),
        ("column_criteria", presentation.column_criteria),
    ):
        if group is not None:
            issues.extend(
                validate_entity_criteria(
                    group, path=f"{path}/{field_name}", is_root=True, registries=registries, check_ergonomics=True
                )
            )
            issues.extend(validate_depth_cap(group, path=f"{path}/{field_name}", registries=registries))
    return issues
