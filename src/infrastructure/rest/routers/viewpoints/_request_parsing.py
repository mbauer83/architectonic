"""Payload validation and error mapping for the viewpoint execution routes.

Every route that accepts an ad-hoc ``query`` or an inline ``presentation`` parses it through
here, so a malformed payload always reaches the caller the same way: a 400 carrying the
parser's own sentence and the field it names. The parsers signal structural problems as
plain ``ValueError``; letting one escape a route turns an authoring mistake into an opaque
server error with the diagnostic stranded in the log.
"""

from __future__ import annotations

from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.domain.viewpoints.viewpoint_presentation_parsing import presentation_from_mapping
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec
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
    shape. These routes used to invent a parallel ``{"code", "path", "message"}`` body instead; the
    error-envelope handler reduced it to a status-derived code and dropped the path, so the GUI's
    per-code error surface was unreachable and the raw envelope reached the screen.
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


def parse_query(raw: dict[str, object] | None) -> ExecutableViewpointQuery | None:
    """Validate an ad-hoc query payload. Malformed → 400, exactly as a presentation is."""
    if raw is None:
        return None
    try:
        return query_from_mapping(raw, label="query")
    except ValueError as exc:
        raise rejected_input(str(exc), field="query") from exc


def parse_presentation(raw: dict[str, object] | None) -> PresentationSpec | None:
    """Validate an inline/override presentation payload with the SAME semantic parser saved
    definitions use — no slug/name/version/tier metadata required. Malformed → 400."""
    if raw is None:
        return None
    try:
        return presentation_from_mapping(raw, label="presentation")
    except ValueError as exc:
        raise rejected_input(str(exc), field="presentation") from exc
