"""SignalReadToken (F3.15): a batch pinned to one snapshot goes
unavailable/retry — never partial — when the snapshot activates, the ceiling
changes, a VEX revision lands, or the store lock-cycles mid-evaluation."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from src.application.security_signals.command import IngestBundle, ingest_security_signals
from src.application.security_signals.read_token import snapshot_still_valid, take_snapshot

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


@pytest.fixture()
def env(tmp_path: Path):
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "snap.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield {
        "store": store,
        "snapshots": SQLCipherSnapshotStore(store._thread_conn_or_none),  # noqa: SLF001
        "vex": SQLCipherVexAssessmentStore(store._thread_conn_or_none),  # noqa: SLF001
    }
    store.lock()


def _ingest(env: dict[str, Any], anchor: str = "APP@1") -> None:
    ingest_security_signals(
        IngestBundle(
            anchor_entity_id=anchor,
            request_id=f"req-{next(_counter)}",
            components=({"component_id": "C1", "name": "a", "purl": "pkg:pypi/a@1"},),
            findings=(),
        ),
        store=env["snapshots"],
        new_snapshot_id=lambda: f"SNAP@{next(_counter)}",
        anchor_reader=_AdmissibleAnchors(),
    )


def _take(env: dict[str, Any], ceiling: str = "TLP:RED") -> Any:
    return take_snapshot(
        "APP@1", availability=env["store"], snapshot_store=env["snapshots"],
        vex_store=env["vex"], exposure_ceiling=ceiling,
    )


def _valid(env: dict[str, Any], token: Any, ceiling: str = "TLP:RED") -> bool:
    return snapshot_still_valid(
        token, availability=env["store"], snapshot_store=env["snapshots"],
        vex_store=env["vex"], exposure_ceiling=ceiling,
    )


class TestSnapshotInvalidation:
    def test_unchanged_state_revalidates(self, env: dict[str, Any]) -> None:
        _ingest(env)
        token = _take(env)
        assert _valid(env, token)

    def test_new_activation_invalidates(self, env: dict[str, Any]) -> None:
        _ingest(env)
        token = _take(env)
        _ingest(env)  # supersedes + activates a new snapshot
        assert not _valid(env, token)

    def test_ceiling_change_invalidates(self, env: dict[str, Any]) -> None:
        _ingest(env)
        token = _take(env, ceiling="TLP:RED")
        assert not _valid(env, token, ceiling="TLP:AMBER")

    def test_vex_mutation_mid_evaluation_invalidates(self, env: dict[str, Any]) -> None:
        _ingest(env)
        token = _take(env)
        env["vex"].record_vex_assessment(
            anchor_entity_id="APP@1", canonical_component_id="pkg:pypi/a@1",
            canonical_vulnerability_id="VID@x", vex_status="affected",
            justification="", author="analyst",
        )
        assert not _valid(env, token)

    def test_lock_unlock_cycle_invalidates(self, env: dict[str, Any]) -> None:
        _ingest(env)
        token = _take(env)
        env["store"].lock()
        env["store"].unlock()
        assert not _valid(env, token)

    def test_first_run_appearing_invalidates_a_no_run_snapshot(self, env: dict[str, Any]) -> None:
        token = _take(env)
        assert token.active_snapshot_id is None
        _ingest(env)
        assert not _valid(env, token)
