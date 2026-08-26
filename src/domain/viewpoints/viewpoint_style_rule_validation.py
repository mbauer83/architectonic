"""Per-rule validation for ``styling_rules``: capability/representation pairing, per-mode
field coherence (match criteria, half-open range bands, scale attribute + token pair),
endpoint sub-criteria (edge rules only), style-value vocabulary, and the quarantine
contract (a ``disabled`` rule is validated for nothing — it must stay saveable exactly as
inherited)."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    issue,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_criteria import (
    ORDERED_ATTRIBUTE_TYPES,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
)
from src.domain.viewpoints.viewpoint_criteria_validation import (
    validate_connection_criteria,
    validate_depth_cap,
    validate_entity_criteria,
)
from src.domain.viewpoints.viewpoint_style_values import is_valid_style_value, style_value_error
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoints import StyleRule


def style_value_issues(capability: str, values: tuple[tuple[str, str], ...]) -> list[ViewpointValidationIssue]:
    """One ``unknown-style-value`` error per ``(path, value)`` outside *capability*'s
    value domain (color capabilities: token or ``#rrggbb``; notation capabilities:
    semantic tokens; anything else is free-form and never flagged)."""
    return [
        issue("error", "unknown-style-value", path, style_value_error(capability, value))
        for path, value in values
        if not is_valid_style_value(capability, value)
    ]


def _validate_range_bands(rule: StyleRule, *, path: str) -> list[ViewpointValidationIssue]:
    issues: list[ViewpointValidationIssue] = []
    bands = sorted(
        rule.range_bands,
        key=lambda band: (band.minimum is not None, band.minimum if band.minimum is not None else float("-inf")),
    )
    for position in range(len(bands) - 1):
        current = bands[position]
        following = bands[position + 1]
        if current.maximum is None or following.minimum is None or current.maximum > following.minimum:
            issues.append(
                issue(
                    "error",
                    "range-band-overlap",
                    f"{path}/range_bands",
                    "range bands must be non-overlapping and half-open",
                )
            )
            break
    return issues


def validate_style_rule(
    rule: StyleRule,
    *,
    path: str,
    representation_capabilities: frozenset[str],
    registries: RegistrySnapshot,
    check_ergonomics: bool,
    declared_derived_names: frozenset[str] = frozenset(),
) -> list[ViewpointValidationIssue]:
    # A quarantined rule is inert by contract: it must stay saveable exactly as inherited
    # (fork-safe), so nothing about it — resolution, mode coherence, values — is validated.
    if rule.disabled:
        return []
    issues: list[ViewpointValidationIssue] = []
    if rule.capability not in representation_capabilities:
        issues.append(
            issue(
                "error",
                "unsupported-capability",
                f"{path}/capability",
                f"capability {rule.capability!r} is unsupported by this representation",
            )
        )
    is_edge_capability = rule.capability.startswith("edge_")
    for endpoint_key, endpoint_criteria in (
        ("source_criteria", rule.source_criteria),
        ("target_criteria", rule.target_criteria),
    ):
        if endpoint_criteria is None:
            continue
        if not is_edge_capability:
            issues.append(
                issue(
                    "error",
                    "endpoint-criteria-on-node-rule",
                    f"{path}/{endpoint_key}",
                    f"{endpoint_key} requires an edge_* capability — node rules have no endpoints",
                )
            )
            continue
        issues.extend(
            validate_entity_criteria(
                endpoint_criteria,
                path=f"{path}/{endpoint_key}",
                is_root=True,
                registries=registries,
                check_ergonomics=check_ergonomics,
            )
        )
    if rule.mode == "match":
        criteria = rule.match_criteria
        if criteria is None:
            issues.append(
                issue(
                    "error", "missing-match-criteria", f"{path}/match_criteria", "mode='match' requires match_criteria"
                )
            )
        elif is_edge_capability != isinstance(criteria, ConnectionCriteriaGroup):
            issues.append(
                issue(
                    "error",
                    "capability-criteria-kind-mismatch",
                    f"{path}/match_criteria",
                    f"capability {rule.capability!r} requires "
                    + ("connection" if is_edge_capability else "entity")
                    + " criteria",
                )
            )
        elif isinstance(criteria, ConnectionCriteriaGroup):
            issues.extend(
                validate_connection_criteria(
                    criteria,
                    path=f"{path}/match_criteria",
                    is_root=True,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
            if check_ergonomics:
                issues.extend(validate_depth_cap(criteria, path=f"{path}/match_criteria", registries=registries))
        elif isinstance(criteria, EntityCriteriaGroup):
            issues.extend(
                validate_entity_criteria(
                    criteria,
                    path=f"{path}/match_criteria",
                    is_root=True,
                    registries=registries,
                    check_ergonomics=check_ergonomics,
                )
            )
            if check_ergonomics:
                issues.extend(validate_depth_cap(criteria, path=f"{path}/match_criteria", registries=registries))
    elif rule.mode == "range":
        if rule.range_attribute is None:
            issues.append(
                issue(
                    "error",
                    "missing-range-attribute",
                    f"{path}/range_attribute",
                    "mode='range' requires range_attribute",
                )
            )
        if check_ergonomics:
            issues.extend(_validate_range_bands(rule, path=path))
    else:
        issues.extend(
            _validate_scale_rule(rule, path=path, registries=registries, declared_derived_names=declared_derived_names)
        )
    issues.extend(_validate_mode_fields(rule, path=path))
    issues.extend(style_value_issues(rule.capability, _rule_style_values(rule, path=path)))
    return issues


def _rule_style_values(rule: StyleRule, *, path: str) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    if rule.value is not None:
        values.append((f"{path}/value", rule.value))
    values.extend((f"{path}/range_bands/{index}/value", band.value) for index, band in enumerate(rule.range_bands))
    values.extend((f"{path}/scale_tokens/{index}", token) for index, token in enumerate(rule.scale_tokens))
    return tuple(values)


def _validate_scale_rule(
    rule: StyleRule,
    *,
    path: str,
    registries: RegistrySnapshot,
    declared_derived_names: frozenset[str] = frozenset(),
) -> list[ViewpointValidationIssue]:
    if rule.scale_attribute is None:
        return [
            issue(
                "error",
                "missing-scale-attribute",
                f"{path}/scale_attribute",
                "mode='scale' requires scale_attribute",
            )
        ]
    context: CriteriaContext = "connection" if rule.capability.startswith("edge_") else "entity"
    declared = resolve_attribute_path(rule.scale_attribute, context=context, registries=registries)
    if rule.scale_attribute.startswith("derived."):
        derived_name = rule.scale_attribute.removeprefix("derived.")
        if derived_name not in declared_derived_names:
            return [
                issue(
                    "error",
                    "unknown-attribute",
                    f"{path}/scale_attribute",
                    f"the query declares no derived attribute named {derived_name!r}",
                )
            ]
    elif declared is None:
        return [issue("error", "unknown-attribute", f"{path}/scale_attribute", "unknown scale attribute")]
    # `ORDERED_ATTRIBUTE_TYPES`, not `NUMERIC_ATTRIBUTE_TYPES`: an ordinal declares its own rank and
    # the comparators already order by it, so a ramp can read it too. The narrower set refused an
    # ordinal scale attribute outright — the wider one already existed, next door, for exactly this
    # question, and the newer feature had reached for the wrong one.
    #
    # A **reserved** path is checked rather than skipped. The guard used to read
    # `declared not in (None, "reserved") and …`, and no reserved path is numeric, date-typed or
    # ordinal, so a scale rule on `status` or `domain` was accepted and then styled nothing — silently
    # on both projection paths, and reported as `expected-empty` ("nothing matched") once the
    # artifact-local path learned to report outcomes at all. A reserved path's type is known, so the
    # refusal belongs at save time where the author can act on it.
    if declared is not None and declared not in ORDERED_ATTRIBUTE_TYPES:
        return [
            issue(
                "error",
                "operator-type-mismatch",
                f"{path}/scale_attribute",
                "scale attributes must be numeric, date, or ordinal values",
            )
        ]
    if len(rule.scale_tokens) != 2:
        return [issue("error", "scale-token-count", f"{path}/scale_tokens", "scale mode requires exactly two tokens")]
    return []


def _validate_mode_fields(rule: StyleRule, *, path: str) -> list[ViewpointValidationIssue]:
    if rule.mode == "match":
        mismatched = rule.range_attribute is not None or bool(rule.range_bands) or any(
            value is not None for value in (rule.scale_attribute, rule.scale_min, rule.scale_max)
        ) or bool(rule.scale_tokens)
    elif rule.mode == "range":
        mismatched = rule.match_criteria is not None or rule.value is not None or any(
            value is not None for value in (rule.scale_attribute, rule.scale_min, rule.scale_max)
        ) or bool(rule.scale_tokens)
    else:
        mismatched = (
            rule.match_criteria is not None
            or rule.value is not None
            or rule.range_attribute is not None
            or bool(rule.range_bands)
        )
    if not mismatched:
        return []
    return [
        issue(
            "error",
            "style-mode-field-mismatch",
            path,
            f"style fields do not match mode {rule.mode!r}",
        )
    ]
