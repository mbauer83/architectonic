"""Audit the generated OpenAPI document against the response *kind* the manifest declares.

One function, used by the fitness test and by nothing else, so the definition of "typed" lives in
one place. An operation satisfies its declared kind when:

* a ``typed`` row's success response is ``application/json`` whose schema is a **named, closed**
  component — no ``additionalProperties: true``, which is how an ``extra="allow"`` model documents an
  object while promising nothing about it. *Which* component is not checked here, deliberately: the
  DTO's identity belongs to the handler that declares it and the module that defines it, and a name
  repeated in the manifest was a second place to be wrong — three of them were wrong about the shape
  they named. What the manifest usefully asserts is that there is a typed body at all;
* a ``bodyless`` row declares 204 with no content — and may declare a 200 *alternative* (the
  dry-run plan of a deletion), which must itself be a named component;
* a ``media`` or ``stream`` row's success response is not ``application/json``.

And, in every case, each declared error status references the shared error envelope.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.rest.route_policy import BODYLESS, MEDIA, STREAM, RouteRow

_SUCCESS_STATUSES = ("200", "201", "204")
_ERROR_ENVELOPE_REF = "#/components/schemas/ErrorEnvelope"


def _success_response(operation: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for status in _SUCCESS_STATUSES:
        response = operation.get("responses", {}).get(status)
        if response is not None:
            return status, response
    return None


def _component_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return ref.rsplit("/", 1)[1]
    return None


def _is_closed(component: dict[str, Any]) -> bool:
    """False when the component says "and possibly anything else"."""
    return component.get("additionalProperties") is not True


def contract_violation(
    row: RouteRow, operation: dict[str, Any], components: dict[str, Any]
) -> str | None:
    """Why *operation* does not satisfy *row*'s declared response contract, or None."""
    if row.response_kind == BODYLESS:
        return _bodyless_violation(operation, components)

    found = _success_response(operation)
    if found is None:
        return "declares no success response"
    _status, response = found
    content = response.get("content") or {}

    if row.response_kind in (MEDIA, STREAM):
        return (
            f"declares application/json, but the kind is {row.response_kind}"
            if "application/json" in content
            else None
        )

    json_body = content.get("application/json")
    if json_body is None:
        return "declares no application/json body"
    name = _component_name(json_body.get("schema") or {})
    if name is None:
        return "declares an inline schema rather than a named component"
    if not _is_closed(components.get(name) or {}):
        return f"{name!r} is open (additionalProperties: true), so it promises nothing"
    return None


def _bodyless_violation(
    operation: dict[str, Any], components: dict[str, Any]
) -> str | None:
    """A bodyless contract: 204 without content, plus an optional named 200 alternative."""
    responses = operation.get("responses") or {}
    no_content = responses.get("204")
    if no_content is None:
        return f"declares no 204, but the contract is {BODYLESS}"
    if no_content.get("content"):
        return "declares a body on its 204"
    alternative = responses.get("200")
    if alternative is None:
        return None
    schema = ((alternative.get("content") or {}).get("application/json") or {}).get("schema") or {}
    if _component_name(schema) is None:
        return "declares a 200 alternative with no named component"
    return None


def error_envelope_violations(operation: dict[str, Any]) -> list[str]:
    """Declared error statuses whose body is not the shared envelope."""
    violations = []
    for status, response in (operation.get("responses") or {}).items():
        if not status.isdigit() or int(status) < 400:
            continue
        schema = ((response.get("content") or {}).get("application/json") or {}).get("schema") or {}
        if schema.get("$ref") != _ERROR_ENVELOPE_REF:
            violations.append(status)
    return violations
