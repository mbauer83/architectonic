"""The MCP ingest tool: capability gating (no ad-hoc write path around the gate),
the typed-outcome projection, and one end-to-end ingest over the REAL SQLCipher
snapshot store — an agent-supplied BOM becomes the anchor's active snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from src.application.security_signals.capability import (
    SignalMutationAllowed,
    SignalMutationDenied,
)
from src.application.security_signals.command import (
    IngestActivated,
    IngestConflict,
    IngestFailed,
    IngestInvalid,
    IngestReplayed,
    IngestValidationError,
)
from src.infrastructure.assurance.signal_ingest import ingest_outcome_payload
from src.infrastructure.mcp.assurance_mcp import security_write_tools
from src.infrastructure.mcp.assurance_mcp.security_write_tools import (
    register_security_write_tools,
)

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

@pytest.fixture(autouse=True)
def _admissible_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat this file's synthetic anchors as real, permitted architecture
    elements.

    The ingest now validates its anchor against the architecture model, which
    these tests deliberately do not stand up. Patching the resolution point keeps
    the transport under test while stating the assumption out loud — a test that
    silently bypassed validation would stop exercising the real path.
    """
    import src.infrastructure.assurance.anchor_reader as anchor_module
    from src.domain.assurance.security_signal_snapshot import AnchorDescriptor

    class _Admissible:
        def describe_anchor(self, entity_id: str) -> AnchorDescriptor:
            return AnchorDescriptor(
                entity_id=entity_id, artifact_type="application-component",
                specialization="service",
            )

    monkeypatch.setattr(anchor_module, "anchor_reader_for", lambda *a, **k: _Admissible())


_BOM: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "serialNumber": "urn:uuid:tool",
    "version": 1,
    "metadata": {"component": {"bom-ref": "root", "name": "app", "version": "1.0"}},
    "components": [
        {"bom-ref": "urllib3", "name": "urllib3", "version": "1.26.0",
         "purl": "pkg:pypi/urllib3@1.26.0"},
    ],
    "dependencies": [{"ref": "root", "dependsOn": ["urllib3"]}],
}

_ADVISORY: dict[str, Any] = {
    "id": "OSV-URLLIB",
    "affected": [{
        "package": {"purl": "pkg:pypi/urllib3"},
        "ranges": [{"type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "1.26.5"}]}],
    }],
}


class _StubContext:
    """The assurance context slice the tool uses, over a real snapshot store."""

    def __init__(self, snapshot_store: object) -> None:
        self.snapshot_store = snapshot_store

    def is_available(self) -> bool:
        return True

    def locked_response(self) -> dict[str, object]:
        return {"error": "assurance_store_locked"}


def _ingest_tool(ctx: _StubContext, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(security_write_tools, "get_assurance_context", lambda: ctx)
    server = FastMCP("test-assurance-write")
    register_security_write_tools(server)
    return server._tool_manager._tools["assurance_ingest_security_signals"].fn  # noqa: SLF001


@pytest.fixture()
def snapshot_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "ingest-tool.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield SQLCipherSnapshotStore(store._thread_conn_or_none)  # noqa: SLF001
    store.lock()


@pytest.fixture()
def allow_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.infrastructure.assurance.signal_gate.current_signal_mutation_capability",
        lambda *, unlocked: SignalMutationAllowed(),
    )


class TestOutcomeProjection:
    def test_activated(self) -> None:
        assert ingest_outcome_payload(IngestActivated("SNAP@1", "SNAP@0", 3, 3, 2, 2)) == {
            "status": "activated",
            "snapshot_id": "SNAP@1",
            "superseded_snapshot_id": "SNAP@0",
            "component_count": 3,
            "finding_count": 2,
            "submitted_component_count": 3,
            "submitted_finding_count": 2,
            "collapsed_finding_count": 0,
        }

    def test_activated_reports_persisted_counts_and_names_the_collapse(self) -> None:
        """The wire body's ``finding_count`` is what a read-back returns, not what
        was submitted; the delta is reported explicitly so alias dedup is
        distinguishable from lost data."""
        payload = ingest_outcome_payload(IngestActivated("SNAP@1", None, 5, 5, 41, 24))

        assert payload["finding_count"] == 24
        assert payload["submitted_finding_count"] == 41
        assert payload["collapsed_finding_count"] == 17

    def test_invalid_reports_every_field_error(self) -> None:
        result = ingest_outcome_payload(IngestInvalid((
            IngestValidationError("anchor_entity_id", "anchor is required"),)))

        assert result["status"] == "invalid"
        assert result["errors"] == [
            {"field": "anchor_entity_id", "message": "anchor is required"}]

    def test_replayed_conflict_and_failed_are_distinguishable(self) -> None:
        replayed = ingest_outcome_payload(IngestReplayed("SNAP@1", "success", "already"))
        conflict = ingest_outcome_payload(IngestConflict("SNAP@1", "reused"))
        failed = ingest_outcome_payload(IngestFailed("SNAP@2", "OperationalError"))

        assert replayed["status"] == "replayed"
        assert replayed["stored_outcome"] == "success"
        assert conflict["status"] == "conflict"
        assert failed["status"] == "failed"
        assert failed["reason"] == "OperationalError"


class TestCapabilityGate:
    def test_locked_store_returns_the_locked_response_and_writes_nothing(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "src.infrastructure.assurance.signal_gate.current_signal_mutation_capability",
            lambda *, unlocked: SignalMutationDenied("store_locked", "locked"),
        )
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)

        assert ingest("APP@1", _BOM) == {"error": "assurance_store_locked"}
        assert snapshot_store.get_active_snapshot("APP@1") is None  # type: ignore[attr-defined]

    def test_non_transactional_configuration_is_a_typed_denial(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "src.infrastructure.assurance.signal_gate.current_signal_mutation_capability",
            lambda *, unlocked: SignalMutationDenied(
                "archive_has_no_atomic_boundary", "no atomic boundary"),
        )
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)

        result = ingest("APP@1", _BOM)

        assert result["error"] == "signal_mutation_denied"
        assert result["reason_code"] == "archive_has_no_atomic_boundary"
        assert snapshot_store.get_active_snapshot("APP@1") is None  # type: ignore[attr-defined]


@pytest.mark.usefixtures("allow_mutation")
class TestIngest:
    def test_supplied_bom_and_advisories_become_the_active_snapshot(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)

        result = ingest("APP@1", _BOM, [_ADVISORY], "req-1")

        assert result["status"] == "activated"
        assert result["component_count"] == 2  # the root plus its dependency
        assert result["finding_count"] == 1
        active = snapshot_store.get_active_snapshot("APP@1")  # type: ignore[attr-defined]
        assert active is not None
        assert active["snapshot_id"] == result["snapshot_id"]
        snapshot_id = str(active["snapshot_id"])
        components = snapshot_store.list_snapshot_components(snapshot_id)  # type: ignore[attr-defined]
        findings = snapshot_store.list_snapshot_findings(snapshot_id)  # type: ignore[attr-defined]
        name_by_row_id = {str(c["component_id"]): c["name"] for c in components}
        assert [name_by_row_id[str(f["component_id"])] for f in findings] == ["urllib3"]

    def test_bom_only_ingest_records_an_inventory_snapshot(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)

        result = ingest("APP@2", _BOM)

        assert result["status"] == "activated"
        assert result["finding_count"] == 0

    def test_replaying_a_request_id_writes_nothing_new(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)
        first = ingest("APP@3", _BOM, [_ADVISORY], "req-replay")

        second = ingest("APP@3", _BOM, [_ADVISORY], "req-replay")

        assert second["status"] == "replayed"
        assert second["snapshot_id"] == first["snapshot_id"]
        assert second["stored_outcome"] == "success"

    def test_reusing_a_request_id_with_a_different_payload_is_a_conflict(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)
        ingest("APP@4", _BOM, [_ADVISORY], "req-conflict")

        second = ingest("APP@4", _BOM, [], "req-conflict")

        assert second["status"] == "conflict"

    def test_a_second_ingest_supersedes_the_previous_snapshot(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)
        first = ingest("APP@5", _BOM, [], "req-a")

        second = ingest("APP@5", _BOM, [], "req-b")

        assert second["superseded_snapshot_id"] == first["snapshot_id"]

    def test_missing_anchor_is_a_typed_validation_failure(
        self, snapshot_store: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingest = _ingest_tool(_StubContext(snapshot_store), monkeypatch)

        result = ingest("  ", _BOM)

        assert result["status"] == "invalid"
        assert result["errors"][0]["field"] == "anchor_entity_id"
