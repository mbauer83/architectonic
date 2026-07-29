"""Hexagonal ports for the confidential assurance capability.

These Protocols define the boundary between application logic and infrastructure.
Adapters live in src/infrastructure/assurance/.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConfidentialAssuranceStore(Protocol):
    """Port for the confidential assurance graph store.

    The live source of truth for all STPA/CAST/GRC entities and edges.
    Adapters: SQLCipherAssuranceStore (default), FakeAssuranceStore (tests).
    """

    def is_unlocked(self) -> bool: ...

    def unlock(self) -> None: ...

    def lock(self) -> None: ...

    # ── Analysis aggregate ──────────────────────────────────────────────────────
    # An analysis is the aggregate root of a unit of STPA/CAST/GRC work: every
    # node belongs to one analysis, and an analysis is anchored to one
    # architecture artifact. Application services enforce the invariants.

    def create_analysis(
        self,
        name: str,
        method: str,
        architecture_anchor_id: str = "",
        *,
        tlp: str = "TLP:WHITE",
        status: str = "draft",
    ) -> str: ...

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None: ...

    def list_analyses(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]: ...

    def update_analysis(self, analysis_id: str, **attrs: object) -> None: ...

    def delete_analysis(self, analysis_id: str) -> None: ...

    # ── Filing and participation ──────────────────────────────────────────────
    # Three relations, not one. A *group* files analyses (flat, no method of its
    # own). `assurance_nodes.analysis_id` records *authorship* — single-valued and
    # fixed, the analysis that produced the node. A *membership* records
    # *participation* — many-to-many, so an FMEA can enumerate failure modes
    # against the control-structure nodes an STPA authored without copying them.
    # One value cannot answer both "who made this" and "who uses this".

    def create_group(self, name: str, description: str = "") -> str: ...

    def get_group(self, group_id: str) -> dict[str, object] | None: ...

    def list_groups(self) -> list[dict[str, object]]: ...

    def delete_group(self, group_id: str) -> None:
        """Remove the group and unfile its analyses; never delete them.

        Filing and content are the same gesture in a UI and must not be the same gesture here:
        a hazard analysis is not disposable because the folder holding it was.
        """
        ...

    def add_analysis_member(self, analysis_id: str, node_id: str) -> None:
        """Draw an existing node into another analysis, leaving its authorship alone.

        Idempotent: "make sure this participates" is what callers mean, and adding the same
        control-structure node to an FMEA twice is not an error worth surfacing.
        """
        ...

    def remove_analysis_member(self, analysis_id: str, node_id: str) -> None:
        """Stop a node participating. The node survives, still owned by its author."""
        ...

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        """Node ids drawn into this analysis from elsewhere, oldest first.

        Authorship is not repeated here: the nodes this analysis wrote are found by
        ``list_nodes(analysis_id=...)``, and the union of the two is what the analysis reasons
        over.
        """
        ...

    def list_participating_analyses(self, node_id: str) -> list[str]:
        """Analyses that draw on this node, excluding the one that authored it."""
        ...

    # ── Node CRUD ─────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict[str, object] | None: ...

    def list_nodes(
        self,
        *,
        node_type: str | None = None,
        status: str | None = None,
        concern_class: str | None = None,
        tlp: str | None = None,
        analysis_id: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        """``sort``/``order`` name a field from
        ``src.application.assurance_node_sorting.NODE_SORT_COLUMNS``; unspecified or
        unrecognised means that module's natural ordering. Ordering happens here, ahead of
        the caller's exposure filter, which preserves relative order."""
        ...

    def create_node(
        self,
        node_type: str,
        name: str,
        *,
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
        attributes: dict[str, object] | None = None,
        content: str = "",
    ) -> str: ...

    def update_node(self, node_id: str, **attrs: object) -> None: ...

    def delete_node(self, node_id: str) -> None: ...

    # ── Edge CRUD ─────────────────────────────────────────────────────────────

    def list_edges(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        conn_type: str | None = None,
    ) -> list[dict[str, object]]: ...

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        conn_type: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> str: ...

    def remove_edge(self, edge_id: str) -> None: ...

    # ── Architecture cross-references ──────────────────────────────────────────

    def register_arch_ref(
        self,
        assurance_node_id: str,
        arch_artifact_id: str,
        ref_type: str,
    ) -> None: ...

    def mark_arch_ref_resolved(
        self,
        assurance_node_id: str,
        arch_artifact_id: str,
        ref_type: str,
    ) -> None: ...

    def list_arch_refs(
        self,
        *,
        assurance_node_id: str | None = None,
        arch_artifact_id: str | None = None,
    ) -> list[dict[str, object]]: ...

    def search_nodes(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, object]]: ...

    # ── Failure-mode factor assessments ───────────────────────────────────────

    def read_fmea_assessments(self, node_ids: Sequence[str]) -> dict[str, list[dict[str, object]]]:
        """Every retained factor revision for the given nodes, keyed by node id.

        Batched by contract, not by convenience: a matrix row needs three factors and a matrix has
        as many rows as the candidate set, so a per-node call would turn one screen into hundreds
        of queries. Superseded revisions come back too — the caller decides which still applies.
        """
        ...

    def write_fmea_assessment(
        self,
        *,
        node_id: str,
        factor: str,
        basis_digest: str,
        value: str,
        justification: str,
        author: str,
    ) -> dict[str, object]:
        """Append one immutable factor revision, allocating its revision number.

        Never an update: the previous revision is what shows a reader that a judgement changed and
        what it was before.
        """
        ...

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, object]: ...


@runtime_checkable
class AssuranceArchive(Protocol):
    """Port for the append-only, hash-chained audit log.

    Separate from the live store — immutable records satisfying EU AI Act Art. 12/18/19/26.
    """

    def append(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]: ...

    def seal_baseline(
        self,
        *,
        notes: str = "",
        analysis_id: str | None = None,
    ) -> dict[str, object]: ...

    def verify_chain(self) -> bool: ...

    def list_entries(
        self,
        *,
        since_seq: int = 0,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]: ...

    def list_baselines(self) -> list[dict[str, object]]: ...

    def head(self) -> dict[str, object] | None: ...


@runtime_checkable
class WORMAssuranceArchive(AssuranceArchive, Protocol):
    """Extended archive port with WORM semantics, legal-hold, and crypto-shredding.

    Opt-in for regulated deployments. The base AssuranceArchive stores records;
    this port additionally supports per-subject envelope encryption, legal holds,
    shredding (DEK destruction), and RFC 3161 timestamp tokens on sealed baselines.
    """

    def provision_subject_key(self, subject_id: str) -> str: ...

    def encrypt_payload(self, subject_id: str, plaintext: str) -> str: ...

    def decrypt_payload(self, subject_id: str, ciphertext_hex: str) -> str: ...

    def shred_subject(self, subject_id: str, *, reason: str = "") -> dict[str, object]: ...

    def set_legal_hold(
        self,
        baseline_id: str,
        *,
        held_by: str = "",
        reason: str = "",
    ) -> str: ...

    def release_legal_hold(self, hold_id: str, *, released_by: str = "") -> None: ...

    def list_legal_holds(self, *, active_only: bool = True) -> list[dict[str, object]]: ...

    def add_timestamp_token(self, baseline_id: str, token_der_hex: str) -> None: ...
