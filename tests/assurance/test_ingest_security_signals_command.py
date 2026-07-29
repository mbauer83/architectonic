"""IngestSecuritySignals command: validation, the wired replay decisions,
failure recording (terminal), end-to-end activation over the REAL SQLCipher
adapter, feed-shrinkage retirement, and same-serial-different-digest ingests
(F3.4/F3.8)."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from src.application.security_signals.command import (
    IngestActivated,
    IngestBundle,
    IngestConflict,
    IngestFailed,
    IngestInvalid,
    IngestReplayed,
    ingest_security_signals,
)

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

class _AdmissibleAnchors:
    """Every anchor in this test file is admissible.

    Stated explicitly rather than skipped: the command now REQUIRES an anchor
    reader, so a test that wants to exercise ingestion has to say its anchor is a
    real, permitted architecture element.
    """

    def describe_anchor(self, entity_id: str):  # type: ignore[no-untyped-def]
        from src.domain.assurance.security_signal_snapshot import AnchorDescriptor

        return AnchorDescriptor(
            entity_id=entity_id, artifact_type="application-component",
            specialization="service",
        )


_counter = itertools.count(1)


def _snapshot_ids() -> Any:
    return lambda: f"SNAP@{next(_counter)}"


@pytest.fixture()
def store(tmp_path: Path):
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "cmd.db"
    init_store(db_path)
    sql_store = SQLCipherAssuranceStore(db_path)
    sql_store.unlock()
    yield SQLCipherSnapshotStore(sql_store._thread_conn_or_none)  # noqa: SLF001
    sql_store.lock()


def _bundle(request_id: str = "req-1", *, findings: tuple = (), components: tuple | None = None,
            bom_serial: str = "urn:uuid:1", diagnostics: dict | None = None) -> IngestBundle:
    return IngestBundle(
        anchor_entity_id="APP@1",
        request_id=request_id,
        components=components if components is not None else (
            {"component_id": "C1", "name": "requests", "purl": "pkg:pypi/requests@2.31.0",
             "directness": "direct"},
        ),
        findings=findings,
        bom_serial=bom_serial,
        diagnostics=diagnostics or {},
    )


class TestValidation:
    def test_missing_anchor_and_bad_finding_are_typed_errors(self, store: Any) -> None:
        bundle = IngestBundle(
            anchor_entity_id="", request_id="r",
            components=({"component_id": "", "name": ""},),
            findings=({"component_id": "ghost", "external_ids": []},),
        )
        result = ingest_security_signals(bundle,
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(result, IngestInvalid)
        fields = {e.field for e in result.errors}
        assert fields == {"anchor_entity_id", "components", "findings"}


class TestExecution:
    def test_successful_ingest_activates_atomically(self, store: Any) -> None:
        result = ingest_security_signals(
            _bundle(findings=({"component_id": "C1", "external_ids": ["CVE-2024-1"]},)),
            store=store, new_snapshot_id=_snapshot_ids(), anchor_reader=_AdmissibleAnchors(),
        )
        assert isinstance(result, IngestActivated)
        assert store.get_active_snapshot("APP@1")["snapshot_id"] == result.snapshot_id
        assert result.persisted_finding_count == 1
        assert result.submitted_finding_count == 1
        assert result.collapsed_finding_count == 0

    def test_reported_counts_are_what_was_persisted_not_what_was_submitted(
        self, store: Any,
    ) -> None:
        """Regression: the ingest used to report ``len(bundle.findings)``, so a
        caller was told 41 findings and then read back 24. Two findings whose
        alias sets resolve to one canonical vulnerability for one component
        collapse to a single row — the reported count must follow the rows."""
        result = ingest_security_signals(
            _bundle(findings=(
                {"component_id": "C1", "external_ids": ["CVE-2024-1"]},
                # Same vulnerability, same component, reached via its GHSA alias.
                {"component_id": "C1", "external_ids": ["GHSA-x", "CVE-2024-1"]},
            )),
            store=store, new_snapshot_id=_snapshot_ids(), anchor_reader=_AdmissibleAnchors(),
        )
        assert isinstance(result, IngestActivated)
        assert result.submitted_finding_count == 2
        assert result.persisted_finding_count == 1
        assert result.collapsed_finding_count == 1
        # The persisted count is exactly what a read of the snapshot returns.
        assert len(store.list_snapshot_findings(result.snapshot_id)) == 1

    def test_second_ingest_supersedes_the_first(self, store: Any) -> None:
        first = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        second = ingest_security_signals(_bundle("req-2"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(first, IngestActivated) and isinstance(second, IngestActivated)
        assert second.superseded_snapshot_id == first.snapshot_id
        assert store.get_active_snapshot("APP@1")["snapshot_id"] == second.snapshot_id

    def test_feed_shrinkage_retires_findings_with_the_superseded_run(self, store: Any) -> None:
        """A vulnerability absent from the new feed simply is not in the new
        active snapshot — metrics read only the active snapshot, so it retires without
        any delete or tombstone (F3.4)."""
        with_finding = _bundle(
            "req-1", findings=({"component_id": "C1", "external_ids": ["CVE-2024-1"]},),
        )
        without_finding = _bundle("req-2")
        ingest_security_signals(with_finding,
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        second = ingest_security_signals(without_finding,
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(second, IngestActivated)
        conn = store.connection.open()
        active_findings = conn.execute(
            "SELECT COUNT(*) AS n FROM snapshot_vulnerability_findings WHERE snapshot_id=?",
            (second.snapshot_id,),
        ).fetchone()["n"]
        assert active_findings == 0
        total_findings = conn.execute(
            "SELECT COUNT(*) AS n FROM snapshot_vulnerability_findings"
        ).fetchone()["n"]
        assert total_findings == 1  # history retained under the superseded snapshot

    def test_same_serial_different_digest_creates_distinct_runs(self, store: Any) -> None:
        """Same BOM serial with changed content is a NEW snapshot under a new
        request_id (F3.8) — serial equality never implies payload equality."""
        first = ingest_security_signals(
            _bundle("req-1", bom_serial="urn:uuid:same"),
            store=store, new_snapshot_id=_snapshot_ids(), anchor_reader=_AdmissibleAnchors(),
        )
        second = ingest_security_signals(
            _bundle("req-2", bom_serial="urn:uuid:same", diagnostics={"unmatched": 1}),
            store=store, new_snapshot_id=_snapshot_ids(), anchor_reader=_AdmissibleAnchors(),
        )
        assert isinstance(first, IngestActivated) and isinstance(second, IngestActivated)
        assert first.snapshot_id != second.snapshot_id


class TestReplay:
    def test_replaying_a_success_returns_the_original_run_without_mutation(self, store: Any) -> None:
        first = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(first, IngestActivated)
        replay = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert replay == IngestReplayed(
            snapshot_id=first.snapshot_id, stored_outcome="success",
            message="This request already succeeded; returning the original snapshot.",
        )
        assert len(store.list_snapshots(anchor_entity_id="APP@1")) == 1

    def test_replaying_an_in_flight_staging_run_says_retry_later(self, store: Any) -> None:
        bundle = _bundle("req-1")
        store.create_staging_snapshot(
            snapshot_id="SNAP@staging", anchor_entity_id="APP@1", request_id="req-1",
            request_payload_digest=bundle.payload_digest(),
        )
        replay = ingest_security_signals(bundle,
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(replay, IngestReplayed)
        assert replay.stored_outcome == "in_progress"
        assert len(store.list_snapshots(anchor_entity_id="APP@1")) == 1

    def test_same_request_different_payload_is_a_conflict_with_no_write(self, store: Any) -> None:
        ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        conflict = ingest_security_signals(
            _bundle("req-1", diagnostics={"changed": True}),
            store=store, new_snapshot_id=_snapshot_ids(), anchor_reader=_AdmissibleAnchors(),
        )
        assert isinstance(conflict, IngestConflict)
        assert len(store.list_snapshots(anchor_entity_id="APP@1")) == 1

    def test_replaying_a_failure_points_at_a_new_request_id(self, store: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        original = store.complete_snapshot

        def _boom(snapshot_id: str) -> None:
            raise RuntimeError("complete blew up")

        monkeypatch.setattr(store, "complete_snapshot", _boom)
        failed = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(failed, IngestFailed)
        monkeypatch.setattr(store, "complete_snapshot", original)
        replay = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(replay, IngestReplayed)
        assert replay.stored_outcome == "failed"
        assert "new request_id" in replay.message
        # And a NEW request id executes fine — failed never resumes, callers move on.
        retry = ingest_security_signals(_bundle("req-2"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(retry, IngestActivated)


class TestFailureRecording:
    def test_populate_error_records_a_failed_run_with_safe_reason(
        self, store: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise ValueError("secret detail that must not leak")

        monkeypatch.setattr(store, "populate_snapshot", _boom)
        result = ingest_security_signals(_bundle("req-1"),
            store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AdmissibleAnchors())
        assert isinstance(result, IngestFailed)
        assert "secret detail" not in result.reason  # type name only
        snapshot = store.find_snapshot_by_request("APP@1", "req-1")
        assert snapshot["status"] == "failed"
        assert "secret detail" not in str(snapshot["failure_reason"])

class TestConcurrentDuplicates:
    def test_concurrent_same_request_yields_one_run(self, store: Any) -> None:
        """Two racing submissions of the same bundle: the UNIQUE(anchor,
        request_id) constraint guarantees at most one staging snapshot is created;
        the loser either replays the stored outcome or surfaces the constraint
        (the write queue serializes real transports on top of this)."""
        import threading

        bundle = _bundle("req-race")
        results: list[object] = []

        def _submit() -> None:
            try:
                results.append(
                    ingest_security_signals(bundle,
                        store=store, new_snapshot_id=_snapshot_ids(),
                        anchor_reader=_AdmissibleAnchors())
                )
            except Exception as exc:  # noqa: BLE001 — constraint loss is acceptable
                results.append(exc)

        threads = [threading.Thread(target=_submit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        snapshots = store.list_snapshots(anchor_entity_id="APP@1")
        assert len(snapshots) == 1
        assert sum(1 for r in results if isinstance(r, IngestActivated)) >= 1


class _NoSuchAnchor:
    def describe_anchor(self, entity_id: str):  # type: ignore[no-untyped-def]
        return None


class _AnchorOfType:
    def __init__(self, artifact_type: str, specialization: str = "") -> None:
        self._type = artifact_type
        self._spec = specialization

    def describe_anchor(self, entity_id: str):  # type: ignore[no-untyped-def]
        from src.domain.assurance.security_signal_snapshot import AnchorDescriptor

        return AnchorDescriptor(
            entity_id=entity_id, artifact_type=self._type, specialization=self._spec)


class TestAnchorValidation:
    """The ingest requires an anchor, so it must also require that the anchor is
    real and is a thing an SBOM can describe — otherwise it stores a snapshot no
    model surface can ever reach."""

    def test_an_anchor_the_model_does_not_know_is_refused(self, store: Any) -> None:
        result = ingest_security_signals(
            _bundle(), store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_NoSuchAnchor(),
        )

        assert isinstance(result, IngestInvalid)
        assert [e.field for e in result.errors] == ["anchor_entity_id"]
        assert "no architecture entity" in result.errors[0].message

    def test_nothing_is_written_when_the_anchor_is_refused(self, store: Any) -> None:
        """Refusal must precede every write — a rejected ingest that had already
        created a staging snapshot would leave the store dirtier than before."""
        ingest_security_signals(
            _bundle(), store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_NoSuchAnchor(),
        )

        assert store.list_snapshots() == []

    @pytest.mark.parametrize("artifact_type, specialization", [
        ("application-component", "module"),    # part of a shipped thing, not one
        ("application-component", "endpoint"),  # an interface, not built at all
        ("business-process", ""),
        ("grouping", ""),               # an aggregate does not ship as one thing
        ("application-collaboration", ""),
    ])
    def test_an_element_an_sbom_cannot_describe_is_refused(
        self, store: Any, artifact_type: str, specialization: str,
    ) -> None:
        result = ingest_security_signals(
            _bundle(), store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AnchorOfType(artifact_type, specialization),
        )

        assert isinstance(result, IngestInvalid)
        assert "cannot anchor security signals" in result.errors[0].message
        # The message names what IS permitted, so the caller can act on it.
        assert "application-component" in result.errors[0].message

    @pytest.mark.parametrize("artifact_type, specialization", [
        ("application-component", ""),
        ("application-component", "service"),
        ("node", ""),               # a container image ships a bill of materials
        ("system-software", ""),    # so does a database engine
    ])
    def test_a_shipped_artifact_is_admissible(
        self, store: Any, artifact_type: str, specialization: str,
    ) -> None:
        result = ingest_security_signals(
            _bundle(), store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AnchorOfType(artifact_type, specialization),
        )

        assert isinstance(result, IngestActivated)

    def test_a_future_specialization_of_a_technology_type_still_qualifies(
        self, store: Any,
    ) -> None:
        """node/system-software declare no specializations today. Enumerating the
        empty case would silently refuse every anchor the moment the ontology
        gained one, so those types admit any specialization."""
        result = ingest_security_signals(
            _bundle(), store=store, new_snapshot_id=_snapshot_ids(),
            anchor_reader=_AnchorOfType("node", "cluster"),
        )

        assert isinstance(result, IngestActivated)
