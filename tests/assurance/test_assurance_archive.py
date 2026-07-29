"""Tests for the append-only hash-chained audit log (AssuranceArchive)."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store_and_archive(tmp_path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    archive = SQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
    yield store, archive
    store.lock()


def test_append_creates_entry(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    entry = archive.append("CREATE", node_id="LSS@1.test", payload={"name": "Loss"})
    assert entry["operation"] == "CREATE"
    assert entry["seq"] == 1
    assert len(entry["entry_hash"]) == 64  # SHA-256 hex


def test_sequential_seqs(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    e1 = archive.append("CREATE", node_id="N1")
    e2 = archive.append("UPDATE", node_id="N1")
    assert e2["seq"] == e1["seq"] + 1


def test_verify_chain_empty(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    assert archive.verify_chain()


def test_verify_chain_with_entries(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    archive.append("CREATE", node_id="N1")
    archive.append("UPDATE", node_id="N1")
    archive.append("DELETE", node_id="N1")
    assert archive.verify_chain()


def test_seal_baseline(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="Initial seal", analysis_id="stpa-001")
    assert baseline["baseline_id"].startswith("BSL@")
    assert baseline["head_seq"] >= 1
    assert len(baseline["head_hash"]) == 64


def test_seal_baseline_empty_log_raises(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    with pytest.raises(RuntimeError, match="empty"):
        archive.seal_baseline()


def test_list_entries(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    archive.append("CREATE", node_id="N1")
    archive.append("CREATE", node_id="N2")
    entries = archive.list_entries()
    assert len(entries) >= 2
    ops = [e["operation"] for e in entries]
    assert "CREATE" in ops


def test_head(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    assert archive.head() is None
    archive.append("CREATE")
    head = archive.head()
    assert head is not None
    assert head["operation"] == "CREATE"


def test_list_baselines(store_and_archive) -> None:  # type: ignore[no-untyped-def]
    _, archive = store_and_archive
    archive.append("CREATE")
    archive.seal_baseline(notes="Seal 1")
    archive.append("UPDATE")
    archive.seal_baseline(notes="Seal 2")
    baselines = archive.list_baselines()
    assert len(baselines) >= 2
