"""Canonicalization and static validation for SET-VALUED (``cardinality: many``) parameters.

A set-valued runtime value is an ordered, duplicate-free tuple, so any permutation or
repetition canonicalizes identically — which is what makes a shared URL, a REST array, and a
CSV provenance column round-trip to the same execution.

Canonical order depends on the vocabulary, and both orders are deterministic:
* CLOSED (``allowed_values`` declared) — declaration order, so the author controls it.
* OPEN (no vocabulary, e.g. a group filter) — sorted, since there is no author-given order.

Membership is only *enforced* for a closed vocabulary. An open set accepts anything: a value
naming nothing in the model yields an empty result, never an error, so a saved filter does not
break when the model changes underneath it.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoint_condition_validation import issue
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue


def canonicalize_set_value(
    values: Sequence[object], allowed_values: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(canonical, unknown)``.

    With a closed vocabulary, ``canonical`` keeps the known members in declaration order and
    ``unknown`` lists the rest (first-seen order, deduplicated). With an OPEN vocabulary every
    member is accepted, ``canonical`` is sorted, and ``unknown`` is always empty.
    """
    supplied = [str(value) for value in values]
    if not allowed_values:
        return tuple(sorted(dict.fromkeys(supplied))), ()
    allowed_index = frozenset(allowed_values)
    present = frozenset(member for member in supplied if member in allowed_index)
    canonical = tuple(name for name in allowed_values if name in present)
    unknown: list[str] = []
    for member in supplied:
        if member not in allowed_index and member not in unknown:
            unknown.append(member)
    return canonical, tuple(unknown)


def set_parameter_issues(parameter: QueryParameter, item_path: str) -> list[ViewpointValidationIssue]:
    """Static validation of a ``cardinality: many`` declaration: a ``min_items`` within the
    vocabulary's bounds, and a default that respects the vocabulary and the minimum."""
    issues: list[ViewpointValidationIssue] = []
    allowed = parameter.allowed_values
    upper = len(allowed) if allowed else None
    if parameter.min_items < 1 or (upper is not None and parameter.min_items > upper):
        bound = f"1 and {upper}" if upper is not None else "at least 1"
        issues.append(issue("error", "set-parameter-invalid-min-items", f"{item_path}/min_items",
                            f"min_items must be {bound}"))
    default = parameter.default
    if default is None:
        return issues
    if not isinstance(default, (list, tuple)):
        issues.append(issue("error", "parameter-type-mismatch", f"{item_path}/default",
                            "a set-valued parameter's default must be a list"))
        return issues
    members = tuple(str(member) for member in default)
    if allowed and set(members) - set(allowed):
        issues.append(issue("error", "parameter-type-mismatch", f"{item_path}/default",
                            "default must be a subset of allowed_values"))
    elif len(members) < parameter.min_items:
        issues.append(issue("error", "set-parameter-below-min-items", f"{item_path}/default",
                            f"default has fewer than min_items ({parameter.min_items}) members"))
    return issues
