"""Recording one factor judgement: validate, append a revision, audit it.

Follows the VEX assessment use case, because it is the same shape of act — an immutable,
attributable judgement about something the model already holds — and a second shape for it would
be a second thing to keep right.

Two departures, both deliberate. A judgement must name the node it is about, and that node must be
a failure mode: rating anything else is a category error the store cannot catch, since its foreign
key only knows the node exists. And every write appends to the audit archive, as any other
assurance mutation does, so a rating that later drives a priority band can be traced to who made it
and when.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.assurance.legacy_invalid import PERMITTED_OPERATION, is_legacy_invalid
from src.application.assurance.ports import AssuranceArchive, ConfidentialAssuranceStore
from src.domain.assurance.fmea_factors import (
    FactorValidationError,
    is_grounded,
    validate_factor_assessment,
)

FAILURE_MODE_NODE_TYPE = "failure-mode"


@dataclass(frozen=True)
class RecordFactorRequest:
    node_id: str
    factor: str
    basis_digest: str
    value: str
    justification: str
    author: str


@dataclass(frozen=True)
class FactorRecorded:
    node_id: str
    factor: str
    revision: int
    value: str
    created_at: str


@dataclass(frozen=True)
class FactorInvalid:
    errors: tuple[FactorValidationError, ...]


@dataclass(frozen=True)
class FactorNodeNotFound:
    node_id: str


@dataclass(frozen=True)
class FactorStoreLocked:
    pass


@dataclass(frozen=True)
class FactorLegacyInvalid:
    """The failure mode awaits provenance repair, so no judgement may be filed against it."""

    node_id: str
    permitted_operation: str = PERMITTED_OPERATION


FactorResult = (
    FactorRecorded | FactorInvalid | FactorNodeNotFound | FactorStoreLocked | FactorLegacyInvalid
)


def record_factor_assessment(
    request: RecordFactorRequest,
    *,
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
) -> FactorResult:
    """Append one factor revision for a failure mode, or report why it was not appended."""
    if not store.is_unlocked():
        return FactorStoreLocked()

    errors = list(validate_factor_assessment(
        request.factor, request.value, request.justification, request.author,
    ))
    if not is_grounded(request.basis_digest):
        # Two ways to have no basis, failing in opposite directions. Absent leaves nothing to retire
        # the judgement, so it would apply forever — the behaviour keying it to a basis prevents.
        # `UNGROUNDED_BASIS` says the picture was never assembled, so the judgement is superseded the
        # moment a reader with the model looks at it, and applies never. Eleven were recorded that
        # way before the report distinguished the two.
        errors.append(FactorValidationError(
            field="basis_digest",
            message="a basis digest is required and must name a picture that was actually read: it "
                    "records the model this judgement was made against, and is what retires the "
                    "judgement when that model moves. A report assembled without the architecture "
                    "model offers no digest to record against — a judgement filed there could never "
                    "apply",
        ))
    if errors:
        return FactorInvalid(errors=tuple(errors))

    node = store.get_node(request.node_id)
    if node is None or str(node.get("node_type")) != FAILURE_MODE_NODE_TYPE:
        return FactorNodeNotFound(request.node_id)
    if is_legacy_invalid(node):
        # A judgement is filed *by* an analysis against a failure mode that analysis owns. With no
        # provenance there is no owner, so there is nobody the judgement could be attributed to.
        return FactorLegacyInvalid(node_id=request.node_id)

    row = store.write_fmea_assessment(
        node_id=request.node_id,
        factor=request.factor,
        basis_digest=request.basis_digest,
        value=request.value,
        justification=request.justification,
        author=request.author,
    )
    archive.append("FMEA_FACTOR_ASSESSED", node_id=request.node_id, payload={
        "factor": request.factor,
        "value": request.value,
        "revision": row["revision"],
        "basis_digest": request.basis_digest,
        "author": request.author,
    })
    return FactorRecorded(
        node_id=request.node_id,
        factor=request.factor,
        revision=int(str(row["revision"])),
        value=request.value,
        created_at=str(row["created_at"]),
    )
