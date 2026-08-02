"""One failure vocabulary across both surfaces, in each surface's own shape.

MCP is JSON-RPC and has no HTTP envelope, so it answers in band: ``{"error": {code, path, message}}``
rather than ``{"detail": {code, message, details, request_id}}``. The *shape* genuinely cannot be
shared. The **codes** can, and until now were not — MCP answered ``execution-timeout``,
``derivation-limit`` and ``binding-cardinality-violation`` for failures REST reports as
``traversal_time_budget_exceeded`` and ``binding_cardinality_violation``, so an agent reading both
surfaces saw two names for one thing. That is the defect 0.2.0 spent itself removing, left standing
on the one surface the HTTP work never touched.

The codes here are members of the REST surface's ``ErrorCode``, and ``test_mcp_error_vocabulary``
holds them to it. Importing the alias is deliberate: a second list would be a second vocabulary
again, one commit later.

``path`` has no REST counterpart — the envelope carries ``details.field_errors[].field`` instead —
and is kept because it is what an MCP client has to locate the offending input with.
"""

from __future__ import annotations

from typing import TypedDict

from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.infrastructure.rest.contracts.errors import ErrorCode


class InBandError(TypedDict):
    """MCP's error shape: no envelope, so the failure travels as the result.

    Constructed as a ``TypedDict`` and returned inside a ``dict[str, object]`` — the tools' own
    return type, which is invariant. The declaration still does its work where it matters: the code
    and the two strings are checked at the point each constructor builds one.
    """

    code: ErrorCode
    path: str
    message: str


def _error(code: ErrorCode, path: str, message: str) -> dict[str, object]:
    return {"error": InBandError(code=code, path=path, message=message)}


def rejected_parameter(exc: ViewpointParameterError) -> dict[str, object]:
    """A parameter the query does not declare, declares as required, or types differently.

    ``validation_error``, as REST reports it. The finer code the exception carries
    (``missing-parameter``, ``parameter-type-mismatch``) is already in the message, which is where
    REST keeps it too — a client branches on the code and reads the message.
    """
    return _error("validation_error", f"parameters/{exc.parameter}", str(exc))


def rejected_input(message: str, *, path: str = "query") -> dict[str, object]:
    """A malformed query or presentation payload."""
    return _error("validation_error", path, message)


def binding_cardinality(exc: BindingCardinalityError) -> dict[str, object]:
    """A binding that resolved to the wrong number of items."""
    return _error("binding_cardinality_violation", "query", str(exc))


def traversal_budget_exceeded(message: str, *, path: str = "query") -> dict[str, object]:
    """The traversal ran out of time or of relationships.

    One code for both, as on the REST surface: the caller's remedy is the same — narrow the query —
    and which bound was reached first is not a distinction they act on differently.
    """
    return _error("traversal_time_budget_exceeded", path, message)
