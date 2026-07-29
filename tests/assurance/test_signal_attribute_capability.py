"""Configured signal-attribute capability over a REAL SQLCipher store:
per-call availability (locked → unavailable; unlock → values — the F3.9 lock
cycle), no fabricated zeros for anchors without an active snapshot, snapshot
mixing protection, and the composition-root selection (configured vs null —
never conditional on the current lock state)."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from src.application.security_signals.command import IngestBundle, ingest_security_signals
from src.application.viewpoints.ports import NullSignalAttributeCapability
from src.infrastructure.assurance.signal_attribute_capability import (
    AssuranceSignalAttributeCapability,
    composed_signal_attribute_capability,
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


class _Context:
    def __init__(self, store: Any, snapshot_store: Any, vex_store: Any) -> None:
        self.store = store
        self.snapshot_store = snapshot_store
        self.vex_store = vex_store
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        return self.store.is_unlocked()


@pytest.fixture()
def ctx(tmp_path: Path):
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "capability.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _Context(
        store,
        SQLCipherSnapshotStore(store._thread_conn_or_none),  # noqa: SLF001
        SQLCipherVexAssessmentStore(store._thread_conn_or_none),  # noqa: SLF001
    )
    store.lock()


def _ingest(ctx: _Context, anchor: str) -> None:
    ingest_security_signals(
        IngestBundle(
            anchor_entity_id=anchor,
            request_id=f"req-{next(_counter)}",
            components=({"component_id": "C1", "name": "a", "purl": "pkg:pypi/a@1"},),
            findings=({"component_id": "C1", "external_ids": ["CVE-2024-1"],
                       "severity_band": "high", "cvss_score": 8.0},),
        ),
        store=ctx.snapshot_store,
        new_snapshot_id=lambda: f"SNAP@{next(_counter)}",
        anchor_reader=_AdmissibleAnchors(),
    )


class TestLockCycle:
    def test_locked_then_unlocked_per_call_availability(self, ctx: _Context) -> None:
        _ingest(ctx, "APP@1")
        capability = AssuranceSignalAttributeCapability(lambda: ctx)  # type: ignore[arg-type]

        ctx.store.lock()
        locked = capability.fetch_metrics(["APP@1"], ["distinct_open_vulnerabilities"])
        assert locked.available is False
        assert "locked" in str(locked.note)

        ctx.store.unlock()
        unlocked = capability.fetch_metrics(["APP@1"], ["distinct_open_vulnerabilities"])
        assert unlocked.available is True
        assert unlocked.values[("APP@1", "distinct_open_vulnerabilities")] == 1


class TestValueSemantics:
    def test_anchor_without_active_run_contributes_no_values(self, ctx: _Context) -> None:
        _ingest(ctx, "APP@1")
        capability = AssuranceSignalAttributeCapability(lambda: ctx)  # type: ignore[arg-type]
        batch = capability.fetch_metrics(
            ["APP@1", "APP@ghost"], ["distinct_open_vulnerabilities"])
        assert batch.available is True
        assert ("APP@1", "distinct_open_vulnerabilities") in batch.values
        assert ("APP@ghost", "distinct_open_vulnerabilities") not in batch.values

    def test_unknown_metric_names_yield_no_values(self, ctx: _Context) -> None:
        _ingest(ctx, "APP@1")
        capability = AssuranceSignalAttributeCapability(lambda: ctx)  # type: ignore[arg-type]
        batch = capability.fetch_metrics(["APP@1"], ["no_such_metric"])
        assert batch.available is True
        assert batch.values == {}

    def test_missing_colocated_stores_are_unavailable(self, ctx: _Context) -> None:
        ctx.snapshot_store = None
        capability = AssuranceSignalAttributeCapability(lambda: ctx)  # type: ignore[arg-type]
        batch = capability.fetch_metrics(["APP@1"], ["finding_total"])
        assert batch.available is False


class TestCompositionRoot:
    def test_disabled_capability_composes_the_null_implementation(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import src.infrastructure.assurance.capability as capability_module

        class _Disabled:
            enabled = False

        monkeypatch.setattr(capability_module, "make_capability", lambda _path: _Disabled())
        composed = composed_signal_attribute_capability()
        assert isinstance(composed, NullSignalAttributeCapability)
        batch = composed.fetch_metrics(["APP@1"], ["finding_total"])
        assert batch.available is False
        assert "not configured" in str(batch.note)
