"""What each refusal carries beyond its code, message and path.

MCP answers in band, so a refusal is the result rather than an envelope around it. The code names
what happened and the message says it in a sentence, but several refusals are only actionable with
data: "in use" without the borrowers is a dead end, and an illegal edge type without the legal set
asks the caller to re-derive what the call already knew.

REST carries the same data under ``details``, typed per code in ``rest.contracts.errors``. These
are the MCP-side counterparts. They are ``TypedDict`` rather than the REST DTOs because MCP returns
plain JSON-able dicts and importing pydantic models here would make the MCP surface depend on the
HTTP one for a shape it does not serve — the *codes* are what the two surfaces share, deliberately,
and that agreement is held by ``test_mcp_error_vocabulary``.
"""

from __future__ import annotations

from typing import TypedDict


class FieldRejection(TypedDict):
    """One field's rejection, with the path a client can use to highlight the input."""

    field: str
    message: str


class ValidationDetails(TypedDict):
    """``validation_error``: which fields were rejected and why."""

    field_errors: list[FieldRejection]


class DuplicateEdgeDetails(TypedDict):
    """``duplicate_edge``: the edge that already states this, so the caller can go and read it."""

    edge_id: str
    source_id: str
    target_id: str
    conn_type: str


class IllegalPairDetails(TypedDict):
    """``illegal_connection_type``: the pair, and every type that *is* legal between it."""

    source_type: str
    target_type: str
    conn_type: str
    legal_types: list[str]


class EntityInUseDetails(TypedDict):
    """``entity_in_use``: who else references the node, because that is the caller's next step."""

    node_id: str
    referencing_analysis_ids: list[str]


class LegacyInvalidDetails(TypedDict):
    """``node_legacy_invalid``: the one operation permitted on a node awaiting provenance repair.

    Named, because an agent told only "refused" will retry the same call.
    """

    node_id: str
    permitted_operation: str


class ProvenanceImmutableDetails(TypedDict):
    """``provenance_immutable``: which analysis already holds the node's provenance."""

    node_id: str
    current_analysis_id: str


class DenialDetails(TypedDict):
    """``signal_mutation_denied``: the machine-readable reason the capability withheld the write."""

    reason_code: str


class ClassificationCeilingDetails(TypedDict):
    """``classification_ceiling_exceeded``: the node's classification against the session's ceiling."""

    node_id: str
    tlp: str
    ceiling: str


class AggregateDetails(TypedDict):
    """The analysis-aggregate invariants that carry a subject and a count.

    ``analysis_not_empty`` reports which analysis and how many nodes it still owns;
    ``analysis_method_mismatch`` and ``invalid_participation`` use the same two fields for their own
    subject. One shape for the three because the caller reads them the same way — a thing, and how
    many of it — and three near-identical dicts would be a distinction without a difference.
    """

    subject: str
    count: int


RefusalDetails = (
    ValidationDetails
    | DuplicateEdgeDetails
    | IllegalPairDetails
    | EntityInUseDetails
    | LegacyInvalidDetails
    | ProvenanceImmutableDetails
    | DenialDetails
    | ClassificationCeilingDetails
    | AggregateDetails
)
