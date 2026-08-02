"""The refusals more than one router package raises, as the published envelope reports them.

Every constructor here turns a failure into an :class:`ApiError` — a closed ``code`` plus the
per-code details DTO — rather than a bare ``HTTPException`` carrying only a sentence. Naming them
once is what keeps two surfaces from describing the same failure two ways, which is the defect
this release exists to remove.

They lived in ``viewpoints/_request_parsing`` while the viewpoint routes were the only caller. They
are not viewpoint vocabulary: the connections router already imported ``derivation_limit`` across
package boundaries for its own neighbour derivation, and the diagram preview needs
``rejected_input`` for a scope entity its diagram type cannot use. A refusal reached for by three
router packages belongs beside them, not inside one of them.

What stays in a router package is the *parsing* that produces these — ``parse_query`` and
``parse_presentation`` are about the viewpoint payload's grammar, not about how a refusal is
reported.
"""

from __future__ import annotations

from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    BindingCardinalityDetails,
    DiagramRenderLimitDetails,
    FieldError,
    ValidationErrorDetails,
)


def rejected_input(message: str, *, field: str) -> ApiError:
    """A malformed input, as the published envelope reports one.

    ``validation_error`` with a ``field_errors`` entry, which is what every other rejected input on
    this surface already answers with — including FastAPI's own 422, whose handler builds the same
    shape. The execution routes used to invent a parallel ``{"code", "path", "message"}`` body
    instead; the error-envelope handler reduced it to a status-derived code and dropped the path, so
    the GUI's per-code error surface was unreachable and the raw envelope reached the screen.
    """
    return ApiError(
        400,
        "validation_error",
        message,
        ValidationErrorDetails(field_errors=[FieldError(field=field, message=message)]),
    )


def parameter_error(exc: ViewpointParameterError) -> ApiError:
    """A parameter the query does not declare, declares as required, or types differently.

    The parameter name reaches the caller as ``field_errors[].field``, which is where the GUI reads
    an input path — the same place it reads one for a rejected body field.
    """
    return rejected_input(str(exc), field=f"parameters.{exc.parameter}")


def execution_timeout(message: str) -> ApiError:
    """504. ``traversal_time_budget_exceeded`` already means exactly this, so no new code.

    Raised as an :class:`ApiError` rather than a bare 504: no status in ``_STATUS_CODES`` maps to
    504, so a bare one reported a gateway timeout as ``internal_error``.
    """
    return ApiError(504, "traversal_time_budget_exceeded", message)


def derivation_limit(message: str) -> ApiError:
    """The derived-relationship traversal hit its configured bound. The same budget code."""
    return ApiError(400, "traversal_time_budget_exceeded", message)


def binding_cardinality(exc: BindingCardinalityError) -> ApiError:
    """Which binding, what it declared, what it resolved to — as data, not only as prose."""
    return ApiError(
        400,
        "binding_cardinality_violation",
        str(exc),
        BindingCardinalityDetails(binding=exc.binding, expected=exc.expectation, found=exc.found),
    )


def diagram_render_limit(message: str, *, entity_count: int, max_entities: int) -> ApiError:
    """The result is too large to draw. Both numbers ride along: "too large" without them leaves
    the caller guessing how much to narrow by."""
    return ApiError(
        400,
        "diagram_render_limit",
        message,
        DiagramRenderLimitDetails(entity_count=entity_count, max_entities=max_entities),
    )
