"""VEX assessment store: immutable append-only revisions with audit in the
same transaction, per-key revision numbering, and latest-valid precedence via
the domain helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import src.infrastructure.assurance._vex_assessment_store as vex_module
from src.domain.assurance.vex_assessment import VexAssessmentKey, VexRevision, current_revision, suppresses_finding
from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

KEY = {
    "anchor_entity_id": "APP@1",
    "canonical_component_id": "pkg:pypi/requests@2.31.0",
    "canonical_vulnerability_id": "VID@aaa",
}


@pytest.fixture()
def store(tmp_path: Path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "vex.db"
    init_store(db_path)
    sql_store = SQLCipherAssuranceStore(db_path)
    sql_store.unlock()
    yield SQLCipherVexAssessmentStore(sql_store._thread_conn_or_none)  # noqa: SLF001
    sql_store.lock()


def _record(store: Any, vex_status: str, justification: str = "reviewed") -> dict[str, Any]:
    return store.record_vex_assessment(
        **KEY, vex_status=vex_status, justification=justification, author="analyst",
    )


class TestRevisions:
    def test_revisions_number_sequentially_per_key(self, store: Any) -> None:
        assert _record(store, "under_investigation")["revision"] == 1
        assert _record(store, "not_affected")["revision"] == 2
        other_key = {**KEY, "canonical_vulnerability_id": "VID@bbb"}
        assert store.record_vex_assessment(
            **other_key, vex_status="affected", justification="", author="analyst",
        )["revision"] == 1

    def test_history_is_retained_and_latest_wins(self, store: Any) -> None:
        _record(store, "not_affected")
        _record(store, "affected")
        rows = store.list_vex_revisions(**KEY)
        assert [r["revision"] for r in rows] == [1, 2]
        revisions = [
            VexRevision(
                key=VexAssessmentKey(**KEY), revision=int(r["revision"]),
                vex_status=str(r["vex_status"]), justification=str(r["justification"]),
                author=str(r["author"]), created_at=str(r["created_at"]),
            )
            for r in rows
        ]
        assert not suppresses_finding(current_revision(revisions))

    def test_audit_lands_in_the_same_transaction(
        self, store: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(vex_module, "append_audit_row", _boom)
        with pytest.raises(RuntimeError):
            _record(store, "not_affected")
        monkeypatch.undo()
        assert store.list_vex_revisions(**KEY) == []  # no unaudited mutation survives
