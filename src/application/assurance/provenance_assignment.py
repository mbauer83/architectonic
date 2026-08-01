"""Assigning a node's provenance — the one audited path that may set it.

Provenance is the analysis that *produced* a node. It is single-valued, and once recorded it is
immutable: an analysis's output is a historical fact, and moving a node between analyses would
rewrite what each of them is on record as having found.

That leaves one legitimate transition. Nodes authored before the analysis aggregate existed carry
no provenance at all — 26 of them in the live store at the time of writing — and the only way to
restore the invariant without inventing history is for a person to say which analysis produced
each one. Automatic attribution is not offered: a plausible guess recorded as provenance is worse
than a recorded gap, because it cannot afterwards be told apart from a real attribution.

    unattributed  → analysis A   allowed, audited, here and nowhere else
    analysis A    → analysis A   idempotent; the assertion already holds
    analysis A    → analysis B   refused: provenance_immutable
    analysis A    → none         refused: provenance is not withdrawable

The check and the write are one serialized operation. Two concurrent assignments naming different
analyses must not both succeed, and a read-then-write in application code cannot promise that —
so the store's compare-and-set is what actually decides, and this module's own check exists to
give a caller the reason rather than a bare failure.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.assurance.ports import AssuranceArchive, ConfidentialAssuranceStore


@dataclass(frozen=True)
class ProvenanceAssigned:
    """The node's provenance is now this analysis — newly recorded, or already so."""

    node_id: str
    analysis_id: str
    #: False when the assertion already held. The outcome is the same; the audit trail is not.
    recorded: bool


@dataclass(frozen=True)
class ProvenanceLocked:
    """The confidential store is not unlocked."""


@dataclass(frozen=True)
class ProvenanceNodeNotFound:
    node_id: str


@dataclass(frozen=True)
class ProvenanceAnalysisNotFound:
    analysis_id: str


@dataclass(frozen=True)
class ProvenanceImmutable:
    """The node already has provenance, and it is a different analysis."""

    node_id: str
    current_analysis_id: str
    requested_analysis_id: str


ProvenanceResult = (
    ProvenanceAssigned
    | ProvenanceLocked
    | ProvenanceNodeNotFound
    | ProvenanceAnalysisNotFound
    | ProvenanceImmutable
)


def assign_provenance(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    node_id: str,
    analysis_id: str,
) -> ProvenanceResult:
    """Record which analysis produced a node, for a node that has no provenance yet."""
    if not store.is_unlocked():
        return ProvenanceLocked()
    node = store.get_node(node_id)
    if node is None:
        return ProvenanceNodeNotFound(node_id)
    if store.get_analysis(analysis_id) is None:
        # An analysis that does not exist is the state being repaired, not a new one to write.
        return ProvenanceAnalysisNotFound(analysis_id)
    current = str(node.get("analysis_id") or "")
    if current == analysis_id:
        return ProvenanceAssigned(node_id=node_id, analysis_id=analysis_id, recorded=False)
    if current:
        return ProvenanceImmutable(
            node_id=node_id, current_analysis_id=current, requested_analysis_id=analysis_id
        )
    store.update_node(node_id, analysis_id=analysis_id)
    archive.append(
        "ASSIGN_PROVENANCE", node_id=node_id, payload={"analysis_id": analysis_id}
    )
    return ProvenanceAssigned(node_id=node_id, analysis_id=analysis_id, recorded=True)
