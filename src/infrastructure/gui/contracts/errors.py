"""The one error envelope this surface returns, and the closed set of codes it can carry.

Before this, an error meant one of three shapes depending on which handler produced it:
FastAPI's ``{"detail": "<a sentence>"}`` from 114 raise sites, a hand-built
``{"error": …, "reason_code": …}`` from the assurance routers, and
``{"error": …, "errors": [...]}`` from validation paths. None of them let a client branch on
the cause, because only some of them had a machine-readable one.

The envelope keeps FastAPI's ``detail`` key so the outer shape and ``HTTPException`` handling
survive, and makes its *value* typed:

    {"detail": {"code": "...", "message": "...", "details": {...} | null, "request_id": "..."}}

``details`` is a **closed DTO per code**, never an open map. An open map here would reintroduce
exactly the arbitrary bodies the response-contract work exists to remove — on the path where a
client has least context and most need of structure.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

#: Every code this surface may return. Closed: a new failure mode is a new member here plus a
#: details DTO in ``ERROR_DETAIL_TYPES``, which is what keeps the union honest.
ErrorCode: TypeAlias = Literal[
    # generic, mapped from a bare HTTPException by status
    "bad_request",
    "forbidden",
    "not_found",
    "conflict",
    "validation_error",
    "write_rejected",
    "internal_error",
    # assurance store and signal gating
    "assurance_store_locked",
    "signal_mutation_denied",
    "invalid_vex_assessment",
    # assurance analysis aggregate
    "analysis_method_mismatch",
    "analysis_not_empty",
    "entity_in_use",
    "provenance_immutable",
    "provenance_required",
    "invalid_participation",
    "node_legacy_invalid",
    # viewpoint authoring
    "viewpoint_referenced",
]


class _Details(BaseModel):
    """Base for a code's details payload: closed, so an undeclared key is a validation error."""

    model_config = ConfigDict(extra="forbid")


class FieldError(_Details):
    """One field's rejection, with the path a client can use to highlight the input."""

    field: str
    message: str


class ValidationErrorDetails(_Details):
    """``validation_error`` and ``invalid_vex_assessment``: which fields were rejected and why."""

    field_errors: list[FieldError]


class DenialDetails(_Details):
    """``signal_mutation_denied`` / ``forbidden`` / ``write_rejected``: the capability's own code.

    Carried separately from ``message`` because a client branches on ``reason_code`` — whether a
    denial is retryable is a decision, and re-deriving it by matching on prose is not.
    """

    reason_code: str
    retryable: bool = False


class MethodMismatchDetails(_Details):
    """``analysis_method_mismatch``: a projection asked of an analysis of another method."""

    analysis_id: str
    expected_method: str
    actual_method: str


class AnalysisNotEmptyDetails(_Details):
    """``analysis_not_empty``: how many nodes the analysis authored.

    No reassignment is offered: provenance is immutable, so the only resolutions are to leave
    the nodes or to delete them explicitly.
    """

    analysis_id: str
    authored_node_count: int


class EntityInUseDetails(_Details):
    """``entity_in_use``: which analyses still reference the entity, so the caller can act."""

    node_id: str
    referencing_analysis_ids: list[str]


class ProvenanceImmutableDetails(_Details):
    """``provenance_immutable``: the analysis that already authored this node."""

    node_id: str
    current_analysis_id: str


class InvalidParticipationDetails(_Details):
    """``invalid_participation``: a node cannot participate in its own provenance analysis.

    Refused rather than silently deduplicated — the relation is conceptually invalid, not merely
    already present, and answering 204 would claim a relation exists that must not.
    """

    node_id: str
    analysis_id: str


class LegacyInvalidDetails(_Details):
    """``node_legacy_invalid``: the node predates mandatory provenance and is repair-only."""

    node_id: str
    permitted_operation: str = "assign_provenance"


class ViewpointReferencerRef(_Details):
    """One diagram or matrix pinning a viewpoint, as an error's details carry it."""

    artifact_id: str
    target_kind: Literal["diagram", "matrix"]


class ViewpointReferencedDetails(_Details):
    """``viewpoint_referenced``: the views that still pin the definition a caller asked to delete.

    Its own code rather than the assurance surface's ``entity_in_use``: that one's details name a
    node and the analyses referencing it, and a diagram is not an analysis. Borrowing the field
    names would put assurance vocabulary in a viewpoint response and leave the client decoding a
    lie.
    """

    slug: str
    referencers: list[ViewpointReferencerRef]


#: Code → the DTO its ``details`` carries, or ``None`` where the code needs none.
#: Read as a discriminated union keyed by ``code``; a code absent from this mapping cannot be
#: returned, because ``ApiError`` validates against it.
ERROR_DETAIL_TYPES: dict[str, type[_Details] | None] = {
    "bad_request": None,
    "forbidden": DenialDetails,
    "not_found": None,
    "conflict": None,
    "validation_error": ValidationErrorDetails,
    "write_rejected": DenialDetails,
    "internal_error": None,
    "assurance_store_locked": None,
    "signal_mutation_denied": DenialDetails,
    "invalid_vex_assessment": ValidationErrorDetails,
    "analysis_method_mismatch": MethodMismatchDetails,
    "analysis_not_empty": AnalysisNotEmptyDetails,
    "entity_in_use": EntityInUseDetails,
    "provenance_immutable": ProvenanceImmutableDetails,
    "provenance_required": None,
    "invalid_participation": InvalidParticipationDetails,
    "node_legacy_invalid": LegacyInvalidDetails,
    "viewpoint_referenced": ViewpointReferencedDetails,
}

#: The union a code's ``details`` can be. Named and exported, because ``ApiError`` and the
#: handlers pass values of exactly this type and the base class would be too wide.
ErrorDetails: TypeAlias = (
    ValidationErrorDetails
    | DenialDetails
    | MethodMismatchDetails
    | AnalysisNotEmptyDetails
    | EntityInUseDetails
    | ProvenanceImmutableDetails
    | InvalidParticipationDetails
    | LegacyInvalidDetails
    | ViewpointReferencedDetails
)


class ErrorBody(BaseModel):
    """The value of ``detail``: what went wrong, in a form both a client and a person can use."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: ErrorDetails | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    """The whole error response. ``detail`` is FastAPI's key, kept so nothing else has to move."""

    model_config = ConfigDict(extra="forbid")

    detail: ErrorBody


#: Status → the generic code a bare ``HTTPException`` maps to.
#:
#: There are 114 ``HTTPException(status, "<a sentence>")`` raise sites, and rewriting all of them
#: to carry a code is neither necessary nor honest — most raise a genuinely generic failure. They
#: get the generic code for their status and keep their sentence as ``message``; a raise that has
#: something specific to say raises :class:`ApiError` instead.
_STATUS_CODES: dict[int, ErrorCode] = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    423: "write_rejected",
}


def status_error_code(status_code: int) -> ErrorCode:
    """The generic code for an HTTP status. Anything unmapped is an internal error."""
    return _STATUS_CODES.get(status_code, "internal_error")


class ApiError(Exception):
    """Raised to return a specific, machine-readable failure rather than a generic one.

    Validates its own ``details`` against the code's declared DTO at construction, so a handler
    cannot ship a payload the published contract does not describe.
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(message)
        if code not in ERROR_DETAIL_TYPES:
            raise ValueError(f"Undeclared error code {code!r} — add it to ERROR_DETAIL_TYPES")
        expected = ERROR_DETAIL_TYPES[code]
        if expected is None:
            if details is not None:
                raise ValueError(
                    f"Error code {code!r} declares no details, got {type(details).__name__}"
                )
        elif not isinstance(details, expected):
            raise ValueError(
                f"Error code {code!r} requires {expected.__name__} details, "
                f"got {type(details).__name__}"
            )
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
