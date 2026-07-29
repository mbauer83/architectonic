"""Tests for the WORM archive with per-subject DEK envelope encryption, legal-hold, and crypto-shredding."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
pytest.importorskip("cryptography", reason="cryptography not installed")


@pytest.fixture()
def worm_archive(tmp_path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance._worm_archive import WORMSQLCipherAssuranceArchive  # noqa: PLC0415
    from src.infrastructure.assurance.lifecycle import init_store  # noqa: PLC0415

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    archive = WORMSQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
    yield store, archive
    store.lock()


def test_provision_subject_key_is_idempotent(worm_archive) -> None:
    _, archive = worm_archive
    result1 = archive.provision_subject_key("analysis-001")
    result2 = archive.provision_subject_key("analysis-001")

    assert result1 == "analysis-001"
    assert result2 == "analysis-001"


def test_encrypt_and_decrypt_payload(worm_archive) -> None:
    _, archive = worm_archive
    archive.provision_subject_key("subj-1")

    ciphertext = archive.encrypt_payload("subj-1", "sensitive analysis data")
    assert isinstance(ciphertext, str)
    assert len(ciphertext) > 0

    plaintext = archive.decrypt_payload("subj-1", ciphertext)
    assert plaintext == "sensitive analysis data"


def test_decrypt_different_subject_raises(worm_archive) -> None:
    _, archive = worm_archive
    archive.provision_subject_key("subj-a")
    archive.provision_subject_key("subj-b")

    ct_a = archive.encrypt_payload("subj-a", "data for A")
    with pytest.raises(Exception):
        archive.decrypt_payload("subj-b", ct_a)


def test_shred_makes_payload_unrecoverable(worm_archive) -> None:
    _, archive = worm_archive
    archive.provision_subject_key("victim")

    ct = archive.encrypt_payload("victim", "will be destroyed")
    archive.shred_subject("victim", reason="GDPR erasure request")

    with pytest.raises(RuntimeError, match="shredded"):
        archive.decrypt_payload("victim", ct)


def test_shred_blocked_by_active_hold(worm_archive) -> None:
    store, archive = worm_archive
    archive.provision_subject_key("held-subj")
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="v1")

    archive.set_legal_hold(str(baseline["baseline_id"]), held_by="legal@example.com", reason="litigation")

    with pytest.raises(RuntimeError, match="legal hold"):
        archive.shred_subject("held-subj")


def test_shred_allowed_after_hold_released(worm_archive) -> None:
    _, archive = worm_archive
    archive.provision_subject_key("releasable")
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="v1")

    hold_id = archive.set_legal_hold(str(baseline["baseline_id"]), held_by="ops@example.com")
    archive.release_legal_hold(hold_id, released_by="ops@example.com")

    result = archive.shred_subject("releasable", reason="cleared for shred")
    assert result["subject_id"] == "releasable"
    assert result["shredded_at"] is not None


def test_set_legal_hold_returns_hold_id(worm_archive) -> None:
    _, archive = worm_archive
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="hold test")

    hold_id = archive.set_legal_hold(str(baseline["baseline_id"]), reason="audit hold")

    assert hold_id.startswith("HLD@")


def test_list_legal_holds_active_only(worm_archive) -> None:
    _, archive = worm_archive
    archive.append("CREATE", node_id="N1")
    b1 = archive.seal_baseline(notes="b1")
    b2 = archive.seal_baseline(notes="b2")

    h1 = archive.set_legal_hold(str(b1["baseline_id"]), reason="hold 1")
    archive.set_legal_hold(str(b2["baseline_id"]), reason="hold 2")
    archive.release_legal_hold(h1)

    active = archive.list_legal_holds(active_only=True)
    all_holds = archive.list_legal_holds(active_only=False)

    assert len(active) == 1
    assert len(all_holds) == 2


def test_add_timestamp_token(worm_archive) -> None:
    _, archive = worm_archive
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="ts test")

    archive.add_timestamp_token(str(baseline["baseline_id"]), "deadbeef1234")

    conn = archive._conn()  # noqa: SLF001
    row = conn.execute(
        "SELECT timestamp_token_hex FROM baselines WHERE baseline_id = ?",
        (baseline["baseline_id"],),
    ).fetchone()
    assert row is not None
    assert row["timestamp_token_hex"] == "deadbeef1234"


def test_seal_baseline_inherits_base_behaviour(worm_archive) -> None:
    _, archive = worm_archive
    archive.append("CREATE", node_id="N1")
    baseline = archive.seal_baseline(notes="worm seal")

    assert baseline["baseline_id"].startswith("BSL@")
    assert archive.verify_chain()


def test_shred_appends_audit_entry(worm_archive) -> None:
    _, archive = worm_archive
    archive.provision_subject_key("audit-subj")

    archive.shred_subject("audit-subj", reason="test shred")

    entries = archive.list_entries(operation="SHRED")
    assert any(e["operation"] == "SHRED" for e in entries)
