"""Tests for EncryptedGitArchive — the private-git AssuranceArchive adapter."""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def fernet_and_archive(tmp_path):
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance._encrypted_git_archive import EncryptedGitArchive

    key = Fernet.generate_key()
    fernet = Fernet(key)
    archive = EncryptedGitArchive(tmp_path, fernet_factory=lambda: fernet)
    return fernet, archive, tmp_path


def test_append_writes_enc_file(fernet_and_archive) -> None:
    _, archive, tmp_path = fernet_and_archive
    archive.append("CREATE", node_id="n1", payload={"name": "x"})
    enc_path = tmp_path / "log" / "00000001.enc"
    assert enc_path.exists()
    # Must not be plain-JSON-readable
    with pytest.raises(Exception):
        json.loads(enc_path.read_bytes())


def test_append_writes_chain_jsonl(fernet_and_archive) -> None:
    _, archive, tmp_path = fernet_and_archive
    archive.append("CREATE", node_id="n1", payload={"name": "x"})
    chain_path = tmp_path / "log" / "chain.jsonl"
    assert chain_path.exists()
    lines = [line for line in chain_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row.keys()) == {"seq", "timestamp", "operation", "entry_hash", "prev_hash"}
    assert "payload_json" not in row
    assert "node_id" not in row


def test_verify_chain_intact(fernet_and_archive) -> None:
    _, archive, _ = fernet_and_archive
    archive.append("OP_A", payload={"a": 1})
    archive.append("OP_B", payload={"b": 2})
    archive.append("OP_C", payload={"c": 3})
    assert archive.verify_chain() is True


def test_verify_chain_tampered_jsonl(fernet_and_archive) -> None:
    _, archive, tmp_path = fernet_and_archive
    archive.append("OP_A", payload={"a": 1})
    archive.append("OP_B", payload={"b": 2})

    chain_path = tmp_path / "log" / "chain.jsonl"
    lines = chain_path.read_text().splitlines()
    first = json.loads(lines[0])
    first["entry_hash"] = "deadbeef" * 8  # tamper
    lines[0] = json.dumps(first)
    chain_path.write_text("\n".join(lines) + "\n")

    assert archive.verify_chain() is False


def test_verify_chain_no_decryption_needed(fernet_and_archive) -> None:
    _, archive, tmp_path = fernet_and_archive
    archive.append("OP_A", payload={"a": 1})
    archive.append("OP_B", payload={"b": 2})

    # Replace the Fernet instance with a freshly-generated key (wrong key)
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance._encrypted_git_archive import EncryptedGitArchive

    wrong_key = Fernet.generate_key()
    wrong_fernet = Fernet(wrong_key)
    archive2 = EncryptedGitArchive(tmp_path, fernet_factory=lambda: wrong_fernet)

    # verify_chain reads only chain.jsonl — succeeds despite wrong key
    assert archive2.verify_chain() is True


def test_seal_baseline(fernet_and_archive) -> None:
    _, archive, tmp_path = fernet_and_archive
    archive.append("CREATE", payload={"x": 1})
    result = archive.seal_baseline(notes="r1")

    assert result["baseline_id"].startswith("BSL@")
    baselines_dir = tmp_path / "log" / "baselines"
    enc_files = list(baselines_dir.glob("*.enc"))
    assert len(enc_files) == 1

    baselines = archive.list_baselines()
    assert len(baselines) == 1
    assert baselines[0]["notes"] == "r1"


def test_list_entries_decrypted(fernet_and_archive) -> None:
    _, archive, _ = fernet_and_archive
    archive.append("CREATE", node_id="n1", payload={"name": "node-one"})
    archive.append("UPDATE", node_id="n1", payload={"status": "active"})

    entries = archive.list_entries()
    assert len(entries) == 2
    for entry in entries:
        assert "payload_json" in entry
        assert "operation" in entry
    assert entries[0]["operation"] == "CREATE"
    assert entries[1]["operation"] == "UPDATE"


def test_head(fernet_and_archive) -> None:
    _, archive, _ = fernet_and_archive
    archive.append("FIRST", payload={"n": 1})
    archive.append("SECOND", payload={"n": 2})

    h = archive.head()
    assert h is not None
    assert h["operation"] == "SECOND"
    assert h["seq"] == 2


def test_locked_raises(tmp_path) -> None:
    from src.infrastructure.assurance._encrypted_git_archive import EncryptedGitArchive

    archive = EncryptedGitArchive(tmp_path, fernet_factory=lambda: None)

    with pytest.raises(RuntimeError, match="locked"):
        archive.append("OP")
    with pytest.raises(RuntimeError, match="locked"):
        archive.seal_baseline()
    with pytest.raises(RuntimeError, match="locked"):
        archive.verify_chain()
    with pytest.raises(RuntimeError, match="locked"):
        archive.list_entries()
    with pytest.raises(RuntimeError, match="locked"):
        archive.list_baselines()
    with pytest.raises(RuntimeError, match="locked"):
        archive.head()
