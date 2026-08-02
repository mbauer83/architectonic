"""Bind declared viewpoint parameters to one execution request."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from src.application.viewpoints.ports import RepositoryReadAccess
from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoint_set_parameters import canonicalize_set_value
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery

#: Why a supplied parameter was refused. A closed vocabulary because both transports classify on it
#: and neither should be reading it out of a string — and because the *set* is the useful statement:
#: there are six ways a parameter can fail to match its declaration, and no seventh.
ParameterRejection = Literal[
    "missing",
    "undeclared",
    "type-mismatch",
    "not-a-set",
    "unknown-member",
    "below-minimum",
]


class ViewpointParameterError(ValueError):
    """Raised when supplied query parameters do not match the declaration.

    The message names the parameter and what was wrong with it — ``"anchor: expected entity-id, got
    boolean"``. It used to be ``f"{code}: {parameter}"``, which put a hyphenated code word this
    release retired (``parameter-type-mismatch``) into prose on both surfaces, and said nothing about
    the *expectation* the value failed. Two problems with one cause: a code is not a sentence.

    ``reason`` is the classification, kept as data on the exception. The wire already carries the
    machine-readable part properly — REST answers ``validation_error`` with the parameter as
    ``details.field_errors[].field``, and MCP the same code with the parameter in ``path`` — so
    nothing needed a new field to branch on. What needed fixing was the prose pretending to be one.
    """

    def __init__(self, reason: ParameterRejection, parameter: str, detail: str) -> None:
        super().__init__(f"{parameter}: {detail}")
        self.reason = reason
        self.parameter = parameter


def bind_parameters(
    query: ExecutableViewpointQuery, supplied: Mapping[str, object] | None, read_access: RepositoryReadAccess
) -> dict[str, object]:
    values = dict(supplied or {})
    declared = {parameter.name: parameter for parameter in query.parameters}
    for name in values:
        if name not in declared:
            raise ViewpointParameterError("undeclared", name, "the query declares no such parameter")
    resolved: dict[str, object] = {}
    for name, parameter in declared.items():
        if name not in values:
            if parameter.default is not None:
                resolved[name] = parameter.default
            elif parameter.required:
                raise ViewpointParameterError(
                    "missing", name, "a required parameter with no default was not supplied"
                )
            continue
        value = values[name]
        if parameter.is_set_valued:
            resolved[name] = _bind_set_value(value, parameter)
            continue
        if not _matches_parameter(value, parameter):
            raise ViewpointParameterError(
                "type-mismatch", name,
                f"expected {parameter.value_type}, got {type(value).__name__}",
            )
        if parameter.value_type != "entity-id" or (
            isinstance(value, str) and read_access.get_entity(value) is not None
        ):
            resolved[name] = value
    return resolved


def _bind_set_value(value: object, parameter: QueryParameter) -> tuple[str, ...]:
    """Bind + canonicalize a set-valued parameter: reject a scalar, reject members outside a
    CLOSED vocabulary, and reject a set below the declared ``min_items`` (which subsumes the
    empty-set case). Duplicates and reorderings collapse to one canonical tuple. An OPEN
    vocabulary enforces no membership — an unmatched value yields an empty result, never an
    error, so a saved filter survives model change."""
    if not isinstance(value, (list, tuple)):
        raise ViewpointParameterError(
            "not-a-set", parameter.name,
            f"expected a list of {parameter.value_type} values, got {type(value).__name__}",
        )
    canonical, unknown = canonicalize_set_value(value, parameter.allowed_values)
    if unknown:
        raise ViewpointParameterError(
            "unknown-member", parameter.name,
            f"{sorted(unknown)} are not among the declared values",
        )
    if len(canonical) < parameter.min_items:
        raise ViewpointParameterError(
            "below-minimum", parameter.name,
            f"expected at least {parameter.min_items} values, got {len(canonical)}",
        )
    return canonical


def inactive_parameter_names(
    query: ExecutableViewpointQuery, supplied: Mapping[str, object] | None
) -> frozenset[str]:
    """Declared parameters that are optional, carry no default, and were NOT supplied — the
    only case where a referencing condition may drop out of its conjunction.

    Keyed on what the CALLER supplied, deliberately not on what survived binding: an
    ``entity-id`` that was supplied but resolves to no live entity is dropped by
    ``bind_parameters`` and would look identical here. That is a BROKEN reference, not an
    unused filter — letting it drop would silently widen the result and hide the breakage.
    """
    provided = set(supplied or {})
    return frozenset(
        parameter.name
        for parameter in query.parameters
        if not parameter.required and parameter.default is None and parameter.name not in provided
    )


def anchor_entity_ids(query: ExecutableViewpointQuery, resolved: Mapping[str, object]) -> tuple[str, ...]:
    """Entity ids one execution is anchored on: the resolved values of the query's declared
    ``entity-id`` parameters, deduplicated in declaration order. ``bind_parameters`` has
    already dropped values that resolve to no known entity."""
    values = (
        resolved.get(parameter.name)
        for parameter in query.parameters
        if parameter.value_type == "entity-id"
    )
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str)))


def _matches_parameter(value: object, parameter: QueryParameter) -> bool:
    if parameter.value_type in {"string", "slug", "date", "entity-id"}:
        return isinstance(value, str)
    if parameter.value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if parameter.value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, bool) if parameter.value_type == "boolean" else False
