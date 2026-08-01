"""How an identifier in a URL resolves — the two rules the framework does not give us.

Both are *behavioural* decisions, so the tests assert the outcome rather than the mechanism:
Starlette resolves by declaration order and Vue Router by specificity, and a test that asserted
either mechanism would break on an upgrade that preserved the behaviour.

**An incomplete detail path is not a collection.** ``/api/entities/`` is a detail path whose
identifier is missing, and Starlette's default is to redirect it to ``/api/entities`` — quietly
answering a different question than the one asked. A client that built that URL has a bug, and the
redirect hides it until something depends on the wrong answer.

**A repeated scalar query parameter is a contradiction, not a preference.** ``?id=a&id=b`` asks for
two things through a parameter that names one, and both Starlette and FastAPI silently take the
last. That is the worst available answer: the caller's first value is discarded with no signal, so a
GUI that accumulated a stale parameter shows data for an artifact the user is not looking at.
"""

from __future__ import annotations

from fastapi import Request

from src.infrastructure.rest.contracts.errors import ApiError, FieldError, ValidationErrorDetails


def _scalar_query_parameters(request: Request) -> frozenset[str]:
    """Names the matched route declares as single-valued query parameters.

    Read from the route's solved dependant rather than from a list maintained here, so a parameter
    that is *meant* to repeat — a multi-select filter typed as a sequence — is not rejected.
    """
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return frozenset()
    return frozenset(
        field.alias
        for field in dependant.query_params
        if not _is_sequence_field(field)
    )


def _is_sequence_field(field: object) -> bool:
    """True when a query parameter is declared to take more than one value."""
    from fastapi._compat import field_annotation_is_sequence  # noqa: PLC0415

    annotation = getattr(getattr(field, "field_info", None), "annotation", None)
    return annotation is not None and bool(field_annotation_is_sequence(annotation))


async def reject_repeated_scalar_query_parameters(request: Request) -> None:
    """Refuse a request that supplies a single-valued query parameter more than once.

    Installed as an application-wide dependency: it has to see the *matched* route to know which
    parameters are single-valued, and it has to apply to every operation, because the parameter
    that accumulates a duplicate is never the one anyone thought to guard.
    """
    scalars = _scalar_query_parameters(request)
    if not scalars:
        return
    repeated = sorted(
        name for name in scalars if len(request.query_params.getlist(name)) > 1
    )
    if repeated:
        raise ApiError(
            422,
            "validation_error",
            "A single-valued query parameter was supplied more than once.",
            ValidationErrorDetails(
                field_errors=[
                    FieldError(field=f"query.{name}", message="expected exactly one value")
                    for name in repeated
                ]
            ),
        )
