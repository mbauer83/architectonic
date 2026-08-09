"""Every way the assurance surface refuses, in the shape the architecture surface already used.

The assurance tools answered flat — ``{"error": "not_found", "node_id": …}`` — while the artifact
tools answered ``{"error": {code, path, message}}`` through ``mcp.execution_failure``. Two shapes on
one protocol meant a client had to know which mount it was talking to before it could tell success
from refusal, and the walk that checks coverage had to recognise both (it did not, at first, and
counted assurance refusals as passes).

The *vocabulary* had already converged by hand: ten of the fourteen names these tools emitted were
already members of the REST surface's ``ErrorCode``. What was left was the shape and four words —
``invalid_value``, ``invalid_request`` and ``invalid_factor_assessment`` are all field rejections,
so they are ``validation_error`` with the field in ``path``; ``classification_ceiling_exceeded``
became a member, because withholding a node from a session is not the same fact as refusing to
publish an argument.

One constructor per refusal, rather than dicts built at call sites, so a refusal cannot be spelled
two ways in two tools.
"""

from __future__ import annotations

from src.infrastructure.mcp.execution_failure import failure
from src.infrastructure.mcp.refusal_details import (
    AggregateDetails,
    ClassificationCeilingDetails,
    DenialDetails,
    DuplicateEdgeDetails,
    EntityInUseDetails,
    FieldRejection,
    IllegalPairDetails,
    LegacyInvalidDetails,
    ProvenanceImmutableDetails,
    ValidationDetails,
)
from src.infrastructure.rest.contracts.assurance_invalid_codes import (
    BIND_INVALID_MAPPING,
    BIND_REJECTED_FIELD,
    INVALID_MAPPING,
    REJECTED_FIELD,
)

STORE_LOCKED_MESSAGE = (
    "The confidential assurance store is not unlocked. "
    "Run `arch-assurance unlock` to enable assurance tools."
)


def store_locked() -> dict[str, object]:
    """The store is configured but not open. Every assurance tool can answer this."""
    return failure("assurance_store_locked", "store", STORE_LOCKED_MESSAGE)


def not_found(identifier: str, *, path: str = "node_id") -> dict[str, object]:
    """No such node, analysis, edge or group.

    ``path`` names which input was wrong, which is the part a caller acts on; the identifier is in
    the message rather than a details payload, matching REST, where ``not_found`` declares none.
    """
    return failure("not_found", path, f"No {path.replace('_', ' ')} {identifier!r} exists.")


def rejected_field(field: str, message: str) -> dict[str, object]:
    """A single field the request got wrong.

    ``validation_error`` rather than a per-surface word: this replaced ``invalid_value`` and
    ``invalid_request``, which said the same thing in two more ways.
    """
    details = ValidationDetails(field_errors=[FieldRejection(field=field, message=message)])
    return failure("validation_error", field, message, details)


def rejected_fields(errors: list[FieldRejection], *, path: str = "request") -> dict[str, object]:
    """Several fields at once — the FMEA factor assessment reports all of them together."""
    summary = "; ".join(f"{error['field']}: {error['message']}" for error in errors)
    return failure("validation_error", path, summary, ValidationDetails(field_errors=errors))


def legacy_invalid(node_id: str, permitted_operation: str) -> dict[str, object]:
    """A node awaiting provenance repair. Names the one permitted operation, so a retry differs."""
    return failure(
        "node_legacy_invalid",
        "node_id",
        (
            f"Node {node_id!r} records no analysis that produced it. Only {permitted_operation} "
            "may touch it until its provenance is repaired."
        ),
        LegacyInvalidDetails(node_id=node_id, permitted_operation=permitted_operation),
    )


def duplicate_edge(
    edge_id: str, source_id: str, target_id: str, conn_type: str
) -> dict[str, object]:
    """This edge already exists. A second copy would be counted twice by anything traversing it."""
    return failure(
        "duplicate_edge",
        "conn_type",
        (
            f"'{conn_type}' from {source_id} to {target_id} already exists as {edge_id}. "
            "A second copy would state the same thing twice and be counted twice by anything "
            "that traverses it."
        ),
        DuplicateEdgeDetails(
            edge_id=edge_id, source_id=source_id, target_id=target_id, conn_type=conn_type
        ),
    )


def illegal_connection_type(
    source_type: str, target_type: str, conn_type: str, legal_types: list[str]
) -> dict[str, object]:
    """The ontology matrix forbids this edge between these node types.

    The legal set travels with the refusal: a caller offered the alternatives can correct the call,
    and one told only "illegal" has to go and read the matrix.
    """
    alternatives = (
        f"Legal types for this pair: {', '.join(legal_types)}."
        if legal_types
        else "No edge type is legal for this pair."
    )
    return failure(
        "illegal_connection_type",
        "conn_type",
        f"'{conn_type}' is not a permitted edge type from {source_type} to {target_type}. {alternatives}",
        IllegalPairDetails(
            source_type=source_type,
            target_type=target_type,
            conn_type=conn_type,
            legal_types=legal_types,
        ),
    )


def entity_in_use(node_id: str, referencing_analysis_ids: list[str]) -> dict[str, object]:
    """Other analyses draw on this node, so deleting it would remove their reference silently."""
    count = len(referencing_analysis_ids)
    analyses = "analysis" if count == 1 else "analyses"
    return failure(
        "entity_in_use",
        "node_id",
        (
            f"Node {node_id!r} is referenced by {count} other {analyses}. Remove those references "
            "first — deleting it now would silently remove them."
        ),
        EntityInUseDetails(node_id=node_id, referencing_analysis_ids=referencing_analysis_ids),
    )


def not_a_failure_mode(node_id: str) -> dict[str, object]:
    """A factor rates a failure mode; rating any other node type records a judgement about nothing."""
    return failure(
        "not_a_failure_mode",
        "node_id",
        (
            f"No failure mode with id {node_id!r} — a factor rates a failure mode, and rating any "
            "other node type would record a judgement about nothing."
        ),
    )


def provenance_immutable(node_id: str, current_analysis_id: str) -> dict[str, object]:
    """Provenance is a historical fact; participation is how another analysis draws on the work."""
    return failure(
        "provenance_immutable",
        "analysis_id",
        (
            f"Node {node_id!r} already records {current_analysis_id} as the analysis that produced "
            "it. Provenance is immutable; participation is how another analysis draws on its work."
        ),
        ProvenanceImmutableDetails(node_id=node_id, current_analysis_id=current_analysis_id),
    )


def signal_mutation_denied(reason_code: str, message: str) -> dict[str, object]:
    """The signal-mutation capability withheld the write for a reason other than a locked store."""
    return failure(
        "signal_mutation_denied", "store", message, DenialDetails(reason_code=reason_code)
    )


def classification_ceiling_exceeded(node_id: str, tlp: str, ceiling: str) -> dict[str, object]:
    """The node is classified above what this session may be shown."""
    return failure(
        "classification_ceiling_exceeded",
        "node_id",
        (
            f"Node {node_id!r} is classified {tlp}, above this session's ceiling of {ceiling}. "
            "Open a session cleared for that tier to read it."
        ),
        ClassificationCeilingDetails(node_id=node_id, tlp=tlp, ceiling=ceiling),
    )


def aggregate_invariant(
    error: str, message: str, *, subject: str = "", count: int = 0
) -> dict[str, object]:
    """One of the analysis aggregate's own invariants, translated through the shared table.

    ``AnalysisInvalid`` carries a free-form string. Which member of the closed vocabulary it means,
    and which field it is about, is decided once in ``rest.contracts.assurance_invalid_codes`` and
    read by both surfaces — a table of the same five strings here would be the second vocabulary
    this module exists to avoid. The status in that table is HTTP's business and is ignored.

    An unmapped string is a programming error rather than a caller's, and it fails loudly for the
    reason the REST side gives: a permissive fallback quietly reopens the hole the closed
    vocabulary closes.
    """
    mapped = INVALID_MAPPING.get(error)
    if mapped is None:  # pragma: no cover - the mapping test makes this unreachable
        raise AssertionError(
            f"AnalysisInvalid({error!r}) has no mapping. Add it to INVALID_MAPPING in "
            "rest/contracts/assurance_invalid_codes.py, with a code from the closed vocabulary."
        )
    _status, code = mapped
    path = REJECTED_FIELD.get(error, "analysis_id")
    details = AggregateDetails(subject=subject, count=count) if subject or count else None
    return failure(code, path, message, details)


def bind_invalid(error: str, message: str) -> dict[str, object]:
    """The model-and-bind refusal, through the same shared table as its HTTP counterpart."""
    mapped = BIND_INVALID_MAPPING.get(error)
    if mapped is None:  # pragma: no cover - the mapping test makes this unreachable
        raise AssertionError(
            f"BindInvalid({error!r}) has no mapping. Add it to BIND_INVALID_MAPPING in "
            "rest/contracts/assurance_invalid_codes.py."
        )
    _status, code = mapped
    return failure(code, BIND_REJECTED_FIELD.get(error, "assurance_node_id"), message)
