"""Payload validation and error mapping for the viewpoint execution routes.

Every route that accepts an ad-hoc ``query`` or an inline ``presentation`` parses it through
here, so a malformed payload always reaches the caller the same way: a 400 carrying the
parser's own sentence and the field it names. The parsers signal structural problems as
plain ``ValueError``; letting one escape a route turns an authoring mistake into an opaque
server error with the diagnostic stranded in the log.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_presentation_parsing import presentation_from_mapping
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec


def parameter_error(exc: ViewpointParameterError) -> HTTPException:
    return HTTPException(400, {"code": exc.code, "path": f"parameters/{exc.parameter}", "message": str(exc)})


def execution_error(code: str, message: str, *, path: str = "query") -> HTTPException:
    return HTTPException(400, {"code": code, "path": path, "message": message})


def parse_query(raw: dict[str, object] | None) -> ExecutableViewpointQuery | None:
    """Validate an ad-hoc query payload. Malformed → 400, exactly as a presentation is."""
    if raw is None:
        return None
    try:
        return query_from_mapping(raw, label="query")
    except ValueError as exc:
        raise execution_error("invalid-query", str(exc), path="query") from exc


def parse_presentation(raw: dict[str, object] | None) -> PresentationSpec | None:
    """Validate an inline/override presentation payload with the SAME semantic parser saved
    definitions use — no slug/name/version/tier metadata required. Malformed → 400."""
    if raw is None:
        return None
    try:
        return presentation_from_mapping(raw, label="presentation")
    except ValueError as exc:
        raise execution_error("invalid-presentation", str(exc), path="presentation") from exc
