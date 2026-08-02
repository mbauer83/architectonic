"""Payload validation for the viewpoint execution routes.

Every route that accepts an ad-hoc ``query`` or an inline ``presentation`` parses it through
here, so a malformed payload always reaches the caller the same way: a 400 carrying the
parser's own sentence and the field it names. The parsers signal structural problems as
plain ``ValueError``; letting one escape a route turns an authoring mistake into an opaque
server error with the diagnostic stranded in the log.

How a refusal is *reported* is not this module's business — that vocabulary is shared by three
router packages and lives in :mod:`src.infrastructure.rest.routers._failures`.
"""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_presentation_parsing import presentation_from_mapping
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec
from src.infrastructure.rest.routers._failures import rejected_input


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
