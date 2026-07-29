"""Port for the signal-snapshot store as the IngestSecuritySignals command needs
it. Implemented by the SQLCipher signal-snapshot adapter; low-level lifecycle
transitions exist only here — no transport exposes them directly."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from src.domain.assurance.security_signal_snapshot import AnchorDescriptor, SnapshotPopulation


class SnapshotStore(Protocol):
    def find_snapshot_by_request(self, anchor_entity_id: str, request_id: str) -> Mapping[str, Any] | None: ...

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
    ) -> None: ...

    def populate_snapshot(
        self,
        snapshot_id: str,
        *,
        components: Sequence[Mapping[str, object]],
        findings: Sequence[Mapping[str, object]],
    ) -> SnapshotPopulation: ...

    def complete_snapshot(self, snapshot_id: str) -> None: ...

    def activate_snapshot(self, snapshot_id: str) -> Mapping[str, Any]: ...

    def fail_snapshot(self, snapshot_id: str, *, reason: str) -> None: ...


class AnchorReader(Protocol):
    """What the ingest needs to know about a prospective anchor.

    A read-only port ONTO the architecture model. The dependency direction is
    assurance → architecture, which is the direction already established by
    ``ArchitectureEntityCreator`` in the model-and-bind use case and by the
    one-way arch references: assurance may read and reference architecture;
    architecture never depends on assurance.

    Returns None when the model does not know the id.
    """

    def describe_anchor(self, entity_id: str) -> AnchorDescriptor | None: ...
