"""Whether an unset optional reaches the wire as ``null`` or not at all — and saying so.

A closed DTO with ``field: str | None = None`` serialises an unset optional as ``null``. The
handlers these DTOs replaced *omitted* the key. That difference is invisible to a schema check and
fatal at run time: the frontend's decoders distinguish the two cases (``Schema.optional`` accepts
absent-or-value, ``Schema.NullOr`` accepts null), so a ``null`` where the decoder expected absence
fails the decode, the row is dropped, and a list renders empty with nothing logged. It cost five
browser specs before anything noticed.

``response_model_exclude_none=True`` is the fix per route, but it leaves the *document* lying: the
generated schema still says ``host_diagram_id?: string | null`` for a route that can never send
null. So the type-level contract check — which holds the hand-written decoders against the
generated types — cannot see this class of defect. Worse, the check would demand the decoder accept
a null the server never sends, which is the wrong direction.

This module makes the document tell the truth. A DTO served only by null-omitting routes says so on
itself, ``apply_wire_null_policy`` removes the ``null`` arm from every one of its optionals before
generation, and the generated types then read ``host_diagram_id?: string``. From there the existing
type-level assertion discriminates all three cases on its own, which is why no separate runtime
fixture check is needed:

===============================  ==============================  ============================
client decoder                   truthful generated type          server obligation
===============================  ==============================  ============================
``Schema.optional(X)``           ``field?: X``                    omit the key
``Schema.NullOr(X)``             ``field: X | null``              send ``null``
``Schema.optional(NullOr(X))``   ``field?: X | null``             either
===============================  ==============================  ============================

The claim on the DTO is not taken on trust: ``tests/architecture/test_wire_null_policy.py`` holds
it against every route that can serialise the DTO, in both directions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Schema keyword carrying the claim. An ``x-`` extension so it is legal OpenAPI while it is in the
#: document, and it is removed by :func:`apply_wire_null_policy` before anything reads the document
#: — a consumer that saw it would have to know what it meant, and no consumer should need to.
WIRE_NULLS_KEYWORD = "x-arch-wire-nulls"

#: The only value the keyword takes. Present means "unset optionals are absent"; absent means the
#: permissive default, "an optional may arrive as null".
NULLS_OMITTED = "omitted"


def _mark_nulls_omitted(schema: dict[str, Any]) -> None:
    schema[WIRE_NULLS_KEYWORD] = NULLS_OMITTED


class NullsOmitted(BaseModel):
    """A closed response DTO whose unset optionals never reach the wire.

    Every route that can serialise it must declare ``response_model_exclude_none=True``, and a DTO
    reachable only from such routes must declare *this* — the fitness functions enforce the
    biconditional, so the two cannot drift apart. Do not use it for a DTO that some other route
    serialises permissively: the schema is shared between them, and a claim true on one path and
    false on another is worse than the permissive default.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra=_mark_nulls_omitted)


def omits_nulls(model: type[BaseModel]) -> bool:
    """Whether ``model`` claims its unset optionals are absent from the wire."""
    extra = model.model_config.get("json_schema_extra")
    return extra is _mark_nulls_omitted


def _without_null_arm(property_schema: dict[str, Any]) -> dict[str, Any]:
    """``property_schema`` with the ``null`` alternative removed, or unchanged if it had none.

    A union of exactly two arms collapses into the surviving one so the emitted TypeScript is
    ``string`` rather than a one-member union; keywords the union carried (``title``, ``description``,
    ``default``) stay on the result, because they describe the property and not the arm.
    """
    for keyword in ("anyOf", "oneOf"):
        arms = property_schema.get(keyword)
        if not isinstance(arms, list):
            continue
        surviving = [arm for arm in arms if arm != {"type": "null"}]
        if len(surviving) == len(arms):
            continue
        annotations = {k: v for k, v in property_schema.items() if k != keyword}
        # A property that can *only* be null is always absent under the policy; there is no arm to
        # promote, so the union is left empty-but-legal rather than silently becoming "anything".
        if len(surviving) == 1:
            return {**annotations, **surviving[0]}
        return {**annotations, keyword: surviving}
    return property_schema


def apply_wire_null_policy(document: dict[str, Any]) -> dict[str, Any]:
    """Rewrite ``document`` so a null-omitting DTO's optionals are absent-or-value, not nullable.

    Mutates and returns the same object — FastAPI caches the document it hands back, and copying it
    would leave the cached one untransformed. Idempotent: the keyword is consumed, so a second pass
    finds nothing to do.

    Only a marked schema's *own* properties are rewritten. ``exclude_none`` drops object keys; it
    does not reach inside an array, so ``list[str | None]`` still carries nulls and its item schema
    is left alone. Nested models are separate schemas and carry their own claim, which is what the
    reachability fitness function is for.
    """
    schemas: dict[str, Any] = (document.get("components") or {}).get("schemas") or {}
    for schema in schemas.values():
        if not isinstance(schema, dict) or schema.pop(WIRE_NULLS_KEYWORD, None) != NULLS_OMITTED:
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        required = schema.get("required")
        for name, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                continue
            rewritten = _without_null_arm(property_schema)
            if rewritten is property_schema:
                continue
            properties[name] = rewritten
            # It was nullable, so under the policy it can be absent — even where the annotation
            # carried no default and the schema therefore called it required.
            if isinstance(required, list) and name in required:
                required.remove(name)
        if isinstance(required, list) and not required:
            del schema["required"]
    return document


def install_wire_null_policy(app: "FastAPI") -> None:
    """Make ``app.openapi()`` publish the truthful document."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = apply_wire_null_policy(generate())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
