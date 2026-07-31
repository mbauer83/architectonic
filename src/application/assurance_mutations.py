"""Shared assurance mutation use cases (application layer).

Each function enforces the three-step write protocol:
  1. Check the store is unlocked → MutationLocked if not.
  2. Perform the write on the store.
  3. Append to the audit log.
  4. Run the post-write verifier; return findings in the result.

Writes are NEVER blocked by the verifier — findings are informational.
The safety-disposition safeguard (E503) surfaces as a teaching message in the
findings list when disposition='accepted' is set on a safety/security constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from src.application.assurance_legacy_invalid import (
    PERMITTED_OPERATION,
    refuse_if_legacy_invalid,
)
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.assurance_node_types import CREATABLE_NODE_TYPES
from src.domain.assurance.constraint_dispositions import DispositionRejection, accept_written_value

if TYPE_CHECKING:
    from src.application.assurance_ports import AssuranceArchive, ConfidentialAssuranceStore

# ── Typed outcomes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MutationOk:
    """Write succeeded; payload is the operation result; findings from post-write verify."""

    payload: dict[str, Any]
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MutationLocked:
    """Store not unlocked; translate to HTTP 423 / MCP locked envelope."""


@dataclass(frozen=True)
class MutationNotFound:
    """Node/edge absent; translate to HTTP 404 / MCP not_found."""

    artifact_id: str


@dataclass(frozen=True)
class MutationIllegalPair:
    """Edge create for a (source_type, target_type, conn_type) the ontology's
    exhaustive matrix forbids; translate to HTTP 422 / MCP invalid envelope.
    ``legal_types`` is the full legal set for the pair (possibly empty)."""

    source_type: str
    target_type: str
    conn_type: str
    legal_types: tuple[str, ...]


@dataclass(frozen=True)
class MutationRejected:
    """A write carrying a value outside a closed vocabulary; translate to HTTP 422 /
    MCP invalid envelope. Rejecting at the boundary is what keeps a rule that matches on
    an exact token from silently failing open against a variant spelling."""

    field: str
    value: str
    message: str


@dataclass(frozen=True)
class MutationDuplicateEdge:
    """The graph already states this. Carries the existing edge so a caller can use it.

    Adding a second edge for the same (source, target, type) does not make a stronger claim, it
    makes the same claim twice — and a derivation that counts relationships would count it twice.
    Rejected rather than silently deduplicated, because a caller who did not expect the edge to
    exist has learned something, and one who did gets the id they were going to look up.
    """

    edge_id: str
    source_id: str
    target_id: str
    conn_type: str


@dataclass(frozen=True)
class MutationLegacyInvalid:
    """The node predates mandatory provenance, so only provenance assignment may touch it.

    Its own outcome rather than a rejected field: nothing the caller sent is wrong, and the remedy
    is a different operation rather than a corrected value.
    """

    node_id: str
    permitted_operation: str = PERMITTED_OPERATION


MutationResult = (
    MutationOk | MutationLocked | MutationNotFound | MutationRejected | MutationLegacyInvalid
)

# Only edge creation can be rejected by the ontology matrix or as a duplicate.
EdgeMutationResult = MutationResult | MutationIllegalPair | MutationDuplicateEdge

# ── Post-write verification ────────────────────────────────────────────────────


def _post_write_findings(
    store: ConfidentialAssuranceStore,
    *,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run the full verifier; return findings scoped to node_id (or all when None)."""
    from src.application.verification.assurance_verifier import verify_store  # noqa: PLC0415

    # No architecture graph here, deliberately: the findings that compare the two models are about
    # elements, and this call reports on the one node just written. Answering "the graph shows some
    # other element to be unanalysed" as the outcome of writing this node would bury the response
    # that was asked for.
    result = verify_store(store)
    issues = [
        {
            "severity": i.severity,
            "code": i.code,
            "message": i.message,
            "node_id": i.node_id,
        }
        for i in result.issues
    ]
    if node_id is not None:
        issues = [f for f in issues if not f["node_id"] or f["node_id"] == node_id]
    return issues


def _rejected_disposition(rejection: DispositionRejection) -> MutationRejected:
    return MutationRejected(field="disposition", value=rejection.value, message=rejection.message)


# ── Use cases ──────────────────────────────────────────────────────────────────


def create_node(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    node_type: str,
    name: str,
    status: str = "draft",
    tlp: str = "TLP:WHITE",
    concern_class: str | None = None,
    disposition: str | None = None,
    uca_type: str | None = None,
    failure_type: str | None = None,
    mode: str | None = None,
    binding_status: str | None = None,
    node_role: str | None = None,
    analysis_id: str | None = None,
    content_text: str = "",
    attributes: dict[str, object] | None = None,
) -> MutationResult:
    if not store.is_unlocked():
        return MutationLocked()
    if node_type not in CREATABLE_NODE_TYPES:
        # A rejection, not a success. This used to be a MutationOk carrying an error payload, so the
        # route answered 201 with `{"error": "invalid_node_type"}` — a refusal wearing a created
        # resource's status, and an ad-hoc error shape of exactly the kind the typed envelope
        # replaced. The closed response contract is what surfaced it: a create receipt cannot carry
        # an error, so validating the payload against it failed.
        return MutationRejected(
            field="node_type",
            value=node_type,
            message=(
                f"{node_type!r} is not a creatable node type. Valid types: "
                f"{', '.join(sorted(CREATABLE_NODE_TYPES))}"
            ),
        )
    accepted = accept_written_value(disposition)
    if isinstance(accepted, DispositionRejection):
        return _rejected_disposition(accepted)
    node_id = store.create_node(
        node_type, name,
        status=status, tlp=tlp,
        concern_class=concern_class, disposition=accepted,
        uca_type=uca_type, failure_type=failure_type, mode=mode, binding_status=binding_status,
        node_role=node_role, analysis_id=analysis_id, content=content_text,
        attributes=attributes,
    )
    archive.append(
        "CREATE", node_id=node_id,
        payload={"node_type": node_type, "name": name, "status": status},
    )
    return MutationOk(
        payload={"node_id": node_id, "node_type": node_type, "name": name},
        findings=_post_write_findings(store, node_id=node_id),
    )


def edit_node(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    node_id: str,
    name: str | None = None,
    status: str | None = None,
    tlp: str | None = None,
    concern_class: str | None = None,
    disposition: str | None = None,
    uca_type: str | None = None,
    failure_type: str | None = None,
    mode: str | None = None,
    binding_status: str | None = None,
    node_role: str | None = None,
    content_text: str | None = None,
    attributes: dict[str, object] | None = None,
) -> MutationResult:
    """Edit a node in place.

    Provenance is not editable here. ``assign_provenance`` is the one audited path that may set it,
    and only for a node that has none — an ordinary edit that could re-attribute authorship would
    let an analysis's recorded output be moved silently. A node still awaiting that repair cannot be
    edited at all: see :mod:`src.application.assurance_legacy_invalid`.
    """
    if not store.is_unlocked():
        return MutationLocked()
    if store.get_node(node_id) is None:
        return MutationNotFound(node_id)
    blocked = refuse_if_legacy_invalid(store, node_id)
    if blocked is not None:
        return MutationLegacyInvalid(node_id=blocked.node_id)
    accepted = accept_written_value(disposition)
    if isinstance(accepted, DispositionRejection):
        return _rejected_disposition(accepted)
    updates: dict[str, object] = {}
    for field_name, value in [
        ("name", name), ("status", status), ("tlp", tlp),
        ("concern_class", concern_class), ("disposition", accepted),
        ("uca_type", uca_type), ("failure_type", failure_type), ("mode", mode),
        ("binding_status", binding_status),
        ("node_role", node_role), ("content_text", content_text),
    ]:
        if value is not None:
            updates[field_name] = value
    if attributes is not None:
        updates["attributes"] = attributes
    if updates:
        store.update_node(node_id, **updates)
        archive.append("UPDATE", node_id=node_id, payload={"updated_fields": list(updates)})
    return MutationOk(
        payload={"node_id": node_id, "updated": list(updates)},
        findings=_post_write_findings(store, node_id=node_id),
    )


def delete_node(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    node_id: str,
) -> MutationResult:
    if not store.is_unlocked():
        return MutationLocked()
    node = store.get_node(node_id)
    if node is None:
        return MutationNotFound(node_id)
    store.delete_node(node_id)
    archive.append("DELETE", node_id=node_id, payload={"node_type": node.get("node_type")})
    return MutationOk(payload={"deleted": node_id}, findings=[])


def add_edge(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    source_id: str,
    target_id: str,
    conn_type: str,
    legal_connection_types: Callable[[str, str], frozenset[str]],
    attributes: dict[str, object] | None = None,
) -> EdgeMutationResult:
    if not store.is_unlocked():
        return MutationLocked()
    source_node = store.get_node(source_id)
    if source_node is None:
        return MutationNotFound(source_id)
    target_node = store.get_node(target_id)
    if target_node is None:
        return MutationNotFound(target_id)
    # Either endpoint awaiting provenance blocks the edge: a relation drawn to a record that cannot
    # say who produced it is new work accumulating on top of the gap being repaired.
    for endpoint in (source_id, target_id):
        blocked = refuse_if_legacy_invalid(store, endpoint)
        if blocked is not None:
            return MutationLegacyInvalid(node_id=blocked.node_id)
    source_type = str(source_node.get("node_type", ""))
    target_type = str(target_node.get("node_type", ""))
    legal = legal_connection_types(source_type, target_type)
    if conn_type not in legal:
        return MutationIllegalPair(
            source_type=source_type,
            target_type=target_type,
            conn_type=conn_type,
            legal_types=tuple(sorted(legal)),
        )
    existing = next(
        (
            e for e in store.list_edges(
                source_id=source_id, target_id=target_id, conn_type=conn_type,
            )
        ),
        None,
    )
    if existing is not None:
        return MutationDuplicateEdge(
            edge_id=str(existing["edge_id"]),
            source_id=source_id,
            target_id=target_id,
            conn_type=conn_type,
        )
    edge_id = store.add_edge(source_id, target_id, conn_type, attributes=attributes)
    archive.append("ADD_EDGE", payload={
        "edge_id": edge_id, "source_id": source_id,
        "target_id": target_id, "conn_type": conn_type,
    })
    return MutationOk(
        payload={
            "edge_id": edge_id, "source_id": source_id,
            "target_id": target_id, "conn_type": conn_type,
        },
        findings=_post_write_findings(store, node_id=source_id),
    )


def delete_edge(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    edge_id: str,
) -> MutationResult:
    if not store.is_unlocked():
        return MutationLocked()
    all_edges = store.list_edges()
    edge = next((e for e in all_edges if str(e.get("edge_id", "")) == edge_id), None)
    if edge is None:
        return MutationNotFound(edge_id)
    store.remove_edge(edge_id)
    archive.append("DELETE_EDGE", payload={
        "edge_id": edge_id,
        "source_id": edge.get("source_id"),
        "target_id": edge.get("target_id"),
    })
    return MutationOk(payload={"deleted": edge_id}, findings=[])


def register_arch_ref(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    assurance_node_id: str,
    arch_artifact_id: str,
    ref_type: str,
) -> MutationResult:
    if not store.is_unlocked():
        return MutationLocked()
    if store.get_node(assurance_node_id) is None:
        return MutationNotFound(assurance_node_id)
    # Stored under the stable key, because callers legitimately hold either form and every
    # surface that joins on this column matches by string equality: a control-structure node
    # bound by the full id and a failure mode bound by the short one describe the same element,
    # and unnormalized they are two.
    element_key = canonical_entity_key(arch_artifact_id)
    store.register_arch_ref(assurance_node_id, element_key, ref_type)
    archive.append("ADD_ARCH_REF", node_id=assurance_node_id, payload={
        "arch_artifact_id": element_key, "ref_type": ref_type,
    })
    return MutationOk(
        payload={
            "assurance_node_id": assurance_node_id,
            "arch_artifact_id": element_key,
            "ref_type": ref_type,
            "status": "registered",
        },
        findings=_post_write_findings(store, node_id=assurance_node_id),
    )
