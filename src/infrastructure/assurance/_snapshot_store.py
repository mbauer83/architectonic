"""SQLCipher/SQLite adapter for the security signal-snapshot aggregate.

This class is the PORT IMPLEMENTATION: the single object callers hold, satisfying
``SnapshotStore`` and the read/deletion/impact slices. The operations themselves
live in focused modules — reads, lifecycle mutations, deletion, reverse impact
lookup, canonical-vulnerability resolution — each taking the shared
``SnapshotConnection`` so its dependency on the database is explicit rather than
reached for through this adapter's internals.

The invariants those modules uphold are documented where they are enforced:
anchors are keyed by their STABLE (slug-free) id (``_snapshot_reads``), every
mutation is one transaction that also lands its audit row
(``_snapshot_lifecycle``), and deletion states its blast radius
(``_snapshot_deletion_ops``).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from src.domain.assurance.security_signal_snapshot import SnapshotPopulation
from src.infrastructure.assurance import _snapshot_lifecycle as lifecycle
from src.infrastructure.assurance import _snapshot_reads as reads
from src.infrastructure.assurance._snapshot_connection import SnapshotConnection
from src.infrastructure.assurance._snapshot_deletion_ops import (
    delete_all_for_anchor,
    delete_one_snapshot,
)
from src.infrastructure.assurance._snapshot_lifecycle import SnapshotTransitionError
from src.infrastructure.assurance._vulnerability_impact_ops import (
    list_active_findings_for_vulnerability,
    list_aliases_for_canonical,
    resolve_canonical_id,
)

__all__ = ["SQLCipherSnapshotStore", "SnapshotTransitionError"]


class SQLCipherSnapshotStore:
    """Works over any DB-API connection factory returning a row-dict connection
    (co-located SQLCipher in production; plain SQLite in the deprecated public
    backend's migration tests)."""

    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._connection = SnapshotConnection(conn_factory)

    @property
    def connection(self) -> SnapshotConnection:
        """The connection collaborator this adapter delegates with.

        Public because it is already a declared dependency of every operation
        module rather than an internal detail, and because diagnostics and tests
        legitimately need raw access to the same database — reaching through a
        protected member for that is the pattern this split removed.
        """
        return self._connection

    # ── Reads ─────────────────────────────────────────────────────────────────

    def find_snapshot_by_request(
        self, anchor_entity_id: str, request_id: str,
    ) -> dict[str, Any] | None:
        return reads.find_snapshot_by_request(self._connection, anchor_entity_id, request_id)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return reads.get_snapshot(self._connection, snapshot_id)

    def get_active_snapshot(self, anchor_entity_id: str) -> dict[str, Any] | None:
        return reads.get_active_snapshot(self._connection, anchor_entity_id)

    def list_snapshots(self, *, anchor_entity_id: str | None = None) -> list[dict[str, Any]]:
        return reads.list_snapshots(self._connection, anchor_entity_id=anchor_entity_id)

    def list_snapshot_components(self, snapshot_id: str) -> list[dict[str, Any]]:
        return reads.list_snapshot_components(self._connection, snapshot_id)

    def list_snapshot_findings(self, snapshot_id: str) -> list[dict[str, Any]]:
        return reads.list_snapshot_findings(self._connection, snapshot_id)

    # ── Lifecycle mutations ───────────────────────────────────────────────────

    def create_staging_snapshot(
        self,
        *,
        snapshot_id: str,
        anchor_entity_id: str,
        request_id: str,
        request_payload_digest: str,
        bom_digest: str = "",
        bom_serial: str = "",
        bom_version: str = "",
        generator_metadata: Mapping[str, object] | None = None,
        source_metadata: Mapping[str, object] | None = None,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        lifecycle.create_staging_snapshot(
            self._connection,
            snapshot_id=snapshot_id,
            anchor_entity_id=anchor_entity_id,
            request_id=request_id,
            request_payload_digest=request_payload_digest,
            bom_digest=bom_digest,
            bom_serial=bom_serial,
            bom_version=bom_version,
            generator_metadata=generator_metadata,
            source_metadata=source_metadata,
            diagnostics=diagnostics,
        )

    def populate_snapshot(
        self,
        snapshot_id: str,
        *,
        components: Sequence[Mapping[str, object]],
        findings: Sequence[Mapping[str, object]],
    ) -> SnapshotPopulation:
        return lifecycle.populate_snapshot(
            self._connection, snapshot_id, components=components, findings=findings)

    def complete_snapshot(self, snapshot_id: str) -> None:
        lifecycle.complete_snapshot(self._connection, snapshot_id)

    def fail_snapshot(self, snapshot_id: str, *, reason: str) -> None:
        lifecycle.fail_snapshot(self._connection, snapshot_id, reason=reason)

    def activate_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return lifecycle.activate_snapshot(self._connection, snapshot_id)

    def fail_stale_staging(self, *, started_before_iso: str) -> list[str]:
        return lifecycle.fail_stale_staging(
            self._connection, started_before_iso=started_before_iso)

    # ── Deletion ──────────────────────────────────────────────────────────────

    def delete_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return delete_one_snapshot(self._connection, snapshot_id)

    def delete_anchor_snapshots(self, anchor_entity_id: str) -> list[dict[str, Any]]:
        return delete_all_for_anchor(self._connection, anchor_entity_id)

    # ── Reverse lookup: one vulnerability → the anchors it affects ────────────

    def resolve_canonical_id(self, identifier: str) -> str | None:
        return resolve_canonical_id(self._connection, identifier)

    def list_active_findings_for_vulnerability(self, canonical_id: str) -> list[dict[str, Any]]:
        return list_active_findings_for_vulnerability(self._connection, canonical_id)

    def list_aliases_for_canonical(self, canonical_id: str) -> list[str]:
        return list_aliases_for_canonical(self._connection, canonical_id)
