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

from src.infrastructure.rest.contracts.wire_shape import Closed

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
    # assurance graph shape — each carries data a caller acts on differently, which is why they are
    # members rather than instances of `conflict`
    "duplicate_edge",
    "illegal_connection_type",
    "not_a_failure_mode",
    "traversal_time_budget_exceeded",
    # Kept a member rather than folded into `validation_error`: it carries the list of types the
    # analysis *does* project to, and a field error can only render that as prose. A client offering
    # the alternatives needs them as data.
    "unknown_diagram_type",
    # Same reasoning, one surface over: the guidance catalogue is fixed, so an unknown topic names no
    # resource — and the reply is worth more as the list of topics that do exist than as prose.
    "unknown_guidance_topic",
    # A GSN diagram leaves the confidential store, so publishing one is refused when the argument's
    # effective classification does not permit it. It carries that classification, because the caller's
    # next question is always "how sensitive?" and prose cannot be ranked.
    "classification_not_publishable",
    # the deployment lacks a prerequisite — a statement about the server, not about the request, so
    # neither `conflict` nor `validation_error` describes it
    "not_configured",
    # viewpoint authoring
    "viewpoint_referenced",
]


class _Details(Closed):
    """Base for a code's details payload. Closedness comes from :class:`Closed`; what this base adds
    is the *role* — a payload narrowed to one error code — which is what `ERROR_DETAIL_TYPES` keys."""


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


class DuplicateEdgeDetails(_Details):
    """``duplicate_edge``: the edge that already connects these two nodes this way.

    The existing edge's id, because the caller's next move is usually to use it rather than to create
    another — and "already exists" without saying which leaves them searching for it.
    """

    edge_id: str
    source_id: str
    target_id: str
    conn_type: str


class IllegalConnectionTypeDetails(_Details):
    """``illegal_connection_type``: the pair the caller tried, and what the ontology permits for it.

    The legal set travels with the refusal. A client that has to ask a second endpoint what would have
    been allowed cannot offer a correction, and a human reading "illegal" learns nothing actionable.
    """

    source_type: str
    target_type: str
    conn_type: str
    legal_types: list[str]


class NotAFailureModeDetails(_Details):
    """``not_a_failure_mode``: the node a factor assessment was aimed at.

    The id only. An earlier draft of this DTO also declared the type the node *does* have, which the
    producer does not know — the use case distinguishes "no failure mode with this id" from "some
    other kind of node" not at all, and a field the producer cannot fill would have been published as
    a promise and served as null.
    """

    node_id: str


class UnknownDiagramTypeDetails(_Details):
    """``unknown_diagram_type``: the projection asked for, and the ones this method does draw."""

    diagram_type: str
    analysis_id: str
    method: str
    available: list[str]


class UnknownGuidanceTopicDetails(_Details):
    """``unknown_guidance_topic``: the topic asked for, and the ones this build has guidance for.

    404 rather than a 200 carrying a "no guidance found" message. The catalogue is fixed and the topic
    is a path segment, so an unrecognised one names no resource — and a 200 made every caller inspect
    the body to find out whether it had an answer, which is the shape this release removes.
    """

    topic: str
    available_topics: list[str]


class ClassificationNotPublishableDetails(_Details):
    """``classification_not_publishable``: the effective classification that forbids publication.

    The *argument's*, not the analysis's own — the most sensitive thing it reasons over. A caller who
    knows only that publication was refused cannot tell whether to reclassify a node or to stop.
    """

    effective_tlp: str


class NotConfiguredDetails(_Details):
    """``not_configured``: the capability this deployment lacks.

    A statement about the server, not the request, which is why it is neither a ``conflict`` nor a
    ``validation_error``: nothing the caller sends can fix it, and reporting it as either would send
    them to correct a request that was correct. The remedy is an operator action, so the payload names
    what is missing rather than what was asked for.
    """

    #: The module or capability that is absent — e.g. ``assurance``, ``confidential_store``.
    capability: str
    remedy: str


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
    "duplicate_edge": DuplicateEdgeDetails,
    "illegal_connection_type": IllegalConnectionTypeDetails,
    "not_a_failure_mode": NotAFailureModeDetails,
    # No details: the anchor node is deliberately redacted here — the handler keeps it out of
    # telemetry too — and how far the walk got is not something the caller can act on. `Retry-After`
    # carries the machine-readable part, which is the only actionable thing there is.
    "traversal_time_budget_exceeded": None,
    "unknown_diagram_type": UnknownDiagramTypeDetails,
    "unknown_guidance_topic": UnknownGuidanceTopicDetails,
    "classification_not_publishable": ClassificationNotPublishableDetails,
    "not_configured": NotConfiguredDetails,
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
    | DuplicateEdgeDetails
    | IllegalConnectionTypeDetails
    | NotAFailureModeDetails
    | UnknownDiagramTypeDetails
    | UnknownGuidanceTopicDetails
    | ClassificationNotPublishableDetails
    | NotConfiguredDetails
    | ProvenanceImmutableDetails
    | InvalidParticipationDetails
    | LegacyInvalidDetails
    | ViewpointReferencedDetails
)


class ErrorBody(Closed):
    """The value of ``detail``: what went wrong, in a form both a client and a person can use."""

    code: ErrorCode
    message: str
    details: ErrorDetails | None = None
    request_id: str


class ErrorEnvelope(Closed):
    """The whole error response. ``detail`` is FastAPI's key, kept so nothing else has to move."""

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
        headers: dict[str, str] | None = None,
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
        #: Extra response headers this refusal needs — ``Retry-After`` on a 503, for instance. The
        #: envelope's own headers (``no-store``, the request id) are added by the handler and win, so
        #: a refusal cannot weaken the confidentiality contract by supplying its own.
        self.headers = dict(headers or {})
