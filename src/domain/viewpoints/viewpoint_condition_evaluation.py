"""Leaf-level evaluation for one ``AttributeCondition``: resolves the
condition's attribute and comparison value against a live entity/connection record, then
applies the normative per-comparator × presence semantics table. No coercion — types are
compared as parsed (validation gates comparator/type mismatches at save time); a
TypeError-worthy mismatch that survives to evaluation time anyway (e.g. after schema drift)
is treated as no match for that candidate rather than crashing the whole viewpoint
execution.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND, ordinal_extreme, ordinal_rank
from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    attribute_ordinal_scale,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_criteria import (
    RESERVED_CONNECTION_PATHS,
    RESERVED_ENTITY_PATHS,
    AttributeCondition,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_evaluation_context import (
    CriteriaReadAccess,
    EvaluationEnvironment,
    EvaluationOutcome,
)

Record = EntityRecord | ConnectionRecord

_NUMERIC_COMPARATORS: frozenset[str] = frozenset({"lt", "lte", "gt", "gte"})


def _numeric_compare(comparator: str, candidate: object, expected: object) -> bool:
    try:
        if comparator == "lt":
            return candidate < expected  # type: ignore[operator]
        if comparator == "lte":
            return candidate <= expected  # type: ignore[operator]
        if comparator == "gt":
            return candidate > expected  # type: ignore[operator]
        return candidate >= expected  # type: ignore[operator]
    except TypeError:
        return False


def _compile_like_pattern(pattern: str, *, ignore_case: bool) -> re.Pattern[str]:
    """Translate a SQL-style pattern (``%`` = any run, ``_`` = one character, ``\\`` escapes
    either) into an anchored regex. A trailing lone backslash is treated as a literal
    backslash rather than raising — evaluation never crashes on a malformed pattern."""
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            parts.append(re.escape(pattern[index + 1]))
            index += 2
            continue
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
        index += 1
    flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
    return re.compile("^" + "".join(parts) + "$", flags)


def _like_match(pattern: object, text: object, *, ignore_case: bool) -> bool:
    if not isinstance(pattern, str) or not isinstance(text, str):
        return False
    return _compile_like_pattern(pattern, ignore_case=ignore_case).match(text) is not None


def _reserved_entity_field(record: EntityRecord, head: str) -> tuple[object, bool]:
    if head == "id":
        return record.artifact_id, True
    if head == "name":
        return record.name, True
    if head == "type":
        return record.artifact_type, True
    if head == "specialization":
        return record.specialization, bool(record.specialization)
    if head == "group":
        return record.group, True
    if head == "domain":
        return record.domain, True
    if head == "subdomain":
        return record.subdomain, True
    if head == "status":
        return record.status, True
    if head == "version":
        return record.version, True
    raise AssertionError(f"unhandled reserved entity path {head!r}")


def _reserved_connection_field(record: ConnectionRecord, head: str) -> tuple[object, bool]:
    if head == "id":
        return record.artifact_id, True
    if head == "type":
        return record.conn_type, True
    if head == "specialization":
        return record.specialization, bool(record.specialization)
    raise AssertionError(f"unhandled reserved connection path {head!r}")


def read_attribute_value(
    record: Record, attribute: str, *, context: CriteriaContext, environment: EvaluationEnvironment | None = None
) -> tuple[object, bool]:
    """Read a dotted attribute path off a record: reserved fields first, then ``extra``.
    Returns ``(value, present)`` — shared by condition evaluation and style-rule range
    lookups (``viewpoint_style_evaluation.py``), so both read attributes identically.
    """
    head, _, rest = attribute.partition(".")
    if head == "derived":
        if not isinstance(record, EntityRecord) or not rest or environment is None:
            return None, False
        key = (record.artifact_id, rest)
        return (environment.derived_values[key], True) if key in environment.derived_values else (None, False)
    reserved = RESERVED_ENTITY_PATHS if context == "entity" else RESERVED_CONNECTION_PATHS
    if head in reserved:
        if context == "entity":
            assert isinstance(record, EntityRecord)
            return _reserved_entity_field(record, head)
        assert isinstance(record, ConnectionRecord)
        return _reserved_connection_field(record, head)
    # Entities: the Properties table (decoded into `attributes`) is the user-facing
    # attribute surface; frontmatter `extra` stays as the fallback.
    if isinstance(record, EntityRecord) and isinstance(record.attributes, Mapping) and head in record.attributes:
        value: object = record.attributes[head]
        for part in rest.split(".") if rest else ():
            if isinstance(value, Mapping) and part in value:
                value = value[part]
            else:
                return None, False
        return value, True
    extra: object = record.extra
    if not isinstance(extra, Mapping) or head not in extra:
        return None, False
    value = extra[head]
    for part in rest.split(".") if rest else ():
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            return None, False
    return value, True


def _resolve_attribute_ref(
    attribute: str, *, record: Record, context: CriteriaContext, registries: RegistrySnapshot
) -> tuple[object, frozenset[str], bool]:
    """Resolve a ``ValueRef``'s referenced attribute: ``(value, drift-warnings, resolved?)``."""
    if not attribute:
        return None, frozenset(), False
    declared = resolve_attribute_path(attribute, context=context, registries=registries)
    if declared is None:
        return None, frozenset({attribute}), False
    actual, present = read_attribute_value(record, attribute, context=context)
    return (actual, frozenset(), True) if present else (None, frozenset(), False)


def _resolve_value(
    value: ValueRef,
    *,
    record: Record,
    context: CriteriaContext,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    connection: ConnectionRecord | None,
    environment: EvaluationEnvironment,
) -> tuple[object, frozenset[str], bool]:
    if value.kind == "literal":
        return value.literal, frozenset(), True
    if value.kind == "attribute_of_self":
        return _resolve_attribute_ref(value.attribute or "", record=record, context=context, registries=registries)
    if value.kind == "attribute_of_endpoint":
        if context != "connection" or connection is None or value.endpoint is None:
            return None, frozenset(), False
        endpoint_id = connection.source if value.endpoint == "source" else connection.target
        endpoint_entity = read_access.get_entity(endpoint_id)
        if endpoint_entity is None:
            return None, frozenset(), False
        return _resolve_attribute_ref(
            value.attribute or "", record=endpoint_entity, context="entity", registries=registries
        )
    if value.kind == "parameter":
        name = value.parameter or ""
        if name in environment.parameters:
            return environment.parameters[name], frozenset(), True
        return None, frozenset(), False
    if value.kind == "binding":
        name = value.binding or ""
        if name not in environment.bindings:
            return None, frozenset(), False
        resolved = environment.bindings[name]
        if value.project is not None:
            resolved = _project_binding(resolved, value.project, context, environment)
        if value.aggregate is not None:
            scale = (
                attribute_ordinal_scale(value.project, context=context, registries=registries)
                if value.project is not None
                else None
            )
            resolved = _aggregate(resolved, value.aggregate, ordinal_scale=scale)
        return (resolved, frozenset(), resolved is not None)
    raise AssertionError(f"unhandled value ref kind {value.kind!r}")


def _project_binding(
    value: object, attribute: str, context: CriteriaContext, environment: EvaluationEnvironment
) -> object:
    items = value if isinstance(value, tuple) else (value,)
    projected = tuple(
        found
        for item in items
        if isinstance(item, (EntityRecord, ConnectionRecord))
        for found, present in (read_attribute_value(item, attribute, context=context, environment=environment),)
        if present
    )
    return projected if isinstance(value, tuple) else (projected[0] if projected else None)


def _aggregate(value: object, aggregate: str, *, ordinal_scale: Sequence[str] | None = None) -> object:
    items = value if isinstance(value, tuple) else (value,)
    values = tuple(item for item in items if item is not None)
    if aggregate == "count":
        return len(values)
    if ordinal_scale is not None and aggregate in ("min", "max"):
        return ordinal_extreme(values, highest=aggregate == "max", scale=ordinal_scale)
    if aggregate == "sum":
        return sum(cast(tuple[int | float, ...], values)) if values else 0
    if aggregate == "avg":
        return sum(cast(tuple[int | float, ...], values)) / len(values) if values else None
    if aggregate == "min":
        return min(cast(tuple[str | int | float, ...], values)) if values else None
    if aggregate == "max":
        return max(cast(tuple[str | int | float, ...], values)) if values else None
    raise AssertionError(f"unhandled aggregate {aggregate!r}")


def _compare(
    comparator: str,
    actual: object,
    expected: object,
    quantifier: str | None = None,
    *,
    ordinal_scale: Sequence[str] | None = None,
) -> bool:
    if quantifier is not None:
        values = expected if isinstance(expected, tuple) else ()
        matches = tuple(_compare(comparator, actual, value, ordinal_scale=ordinal_scale) for value in values)
        return any(matches) if quantifier == "any" else all(matches)
    if comparator == "eq":
        if isinstance(actual, (list, tuple)):
            return any(element == expected for element in actual)
        return actual == expected
    if comparator == "neq":
        if isinstance(actual, (list, tuple)):
            return not any(element == expected for element in actual)
        return actual != expected
    if comparator == "in":
        options = expected if isinstance(expected, (list, tuple)) else ()
        if isinstance(actual, (list, tuple)):
            return any(element in options for element in actual)
        return actual in options
    if comparator == "not_in":
        options = expected if isinstance(expected, (list, tuple)) else ()
        if isinstance(actual, (list, tuple)):
            return not any(element in options for element in actual)
        return actual not in options
    if comparator in ("like", "ilike"):
        candidates = actual if isinstance(actual, (list, tuple)) else (actual,)
        ignore_case = comparator == "ilike"
        return any(_like_match(expected, candidate, ignore_case=ignore_case) for candidate in candidates)
    if comparator in _NUMERIC_COMPARATORS:
        candidates = actual if isinstance(actual, (list, tuple)) else (actual,)
        if ordinal_scale is not None:
            # Order by declared rank. A value absent from the scale has no rank, so it takes
            # part in no ordering rather than sorting as the lowest member.
            right = ordinal_rank(expected, ordinal_scale)
            if right is None:
                return False
            ranks = (ordinal_rank(candidate, ordinal_scale) for candidate in candidates)
            return any(
                _numeric_compare(comparator, left, right) for left in ranks if left is not None
            )
        return any(_numeric_compare(comparator, candidate, expected) for candidate in candidates)
    raise AssertionError(f"unhandled comparator {comparator!r}")


def evaluate_attribute_condition(
    condition: AttributeCondition,
    *,
    record: Record,
    context: CriteriaContext,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    connection: ConnectionRecord | None,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
) -> EvaluationOutcome:
    # An unsupplied declared-optional parameter makes this condition assert nothing: it drops
    # out of its conjunction instead of failing to match (which would silently exclude
    # everything whenever an optional filter is omitted). Checked before any attribute work —
    # the condition is inert regardless of what it compares against.
    if condition.value.kind == "parameter" and condition.value.parameter in environment.inactive_parameters:
        return EvaluationOutcome(matched=True, inactive=True)

    derived_path = condition.attribute.startswith("derived.") and isinstance(record, EntityRecord)
    declared = (
        "derived"
        if derived_path
        else resolve_attribute_path(condition.attribute, context=context, registries=registries)
    )
    drift: frozenset[str] = frozenset()
    if declared is None:
        drift = frozenset({condition.attribute})
        actual, present = None, False
    else:
        actual, present = read_attribute_value(record, condition.attribute, context=context, environment=environment)

    if condition.comparator == "exists":
        matched = present
    elif condition.comparator == "absent":
        matched = not present
    elif not present:
        matched = False
    else:
        expected, ref_drift, resolved = _resolve_value(
            condition.value,
            record=record,
            context=context,
            read_access=read_access,
            registries=registries,
            connection=connection,
            environment=environment,
        )
        drift = drift | ref_drift
        scale = (
            attribute_ordinal_scale(condition.attribute, context=context, registries=registries)
            if declared == ORDINAL_KIND and condition.comparator in _NUMERIC_COMPARATORS
            else None
        )
        if scale is not None and ordinal_rank(actual, scale) is None:
            # A stored value outside its declared enum. Reported as drift for the same reason an
            # unknown attribute is: the data and the schema disagree, and the reader needs to know
            # the row took no part in the ordering rather than that it ranked lowest.
            drift = drift | frozenset({condition.attribute})
        matched = resolved and _compare(
            condition.comparator, actual, expected, condition.value.quantifier, ordinal_scale=scale,
        )

    if condition.negate:
        matched = not matched
    return EvaluationOutcome(matched, drift)
