"""Unit tests for S3WORMAssuranceArchive using moto."""

from __future__ import annotations

import pytest

moto_mod = pytest.importorskip("moto", reason="moto not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")


@pytest.fixture
def s3_archive():
    from moto import mock_aws

    with mock_aws():
        import boto3 as _boto3

        _boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="test-worm-bucket",
            ObjectLockEnabledForBucket=True,
        )
        from src.infrastructure.assurance._s3_worm_archive import S3WORMAssuranceArchive

        archive = S3WORMAssuranceArchive(
            bucket="test-worm-bucket",
            prefix="arch-assurance/",
            region="us-east-1",
        )
        yield archive


def test_append_single_entry(s3_archive):
    result = s3_archive.append("CREATE", node_id="n1", payload={"name": "test"})
    assert result["seq"] == 1
    assert result["operation"] == "CREATE"
    assert len(result["entry_hash"]) == 64


def test_verify_chain_empty(s3_archive):
    assert s3_archive.verify_chain() is True


def test_verify_chain_multiple_entries(s3_archive):
    s3_archive.append("CREATE", node_id="n1")
    s3_archive.append("UPDATE", node_id="n1", payload={"status": "active"})
    s3_archive.append("DELETE", node_id="n1")
    assert s3_archive.verify_chain() is True
    assert s3_archive.head()["seq"] == 3  # type: ignore[index]


def test_seal_baseline(s3_archive):
    s3_archive.append("CREATE", node_id="sys1")
    baseline = s3_archive.seal_baseline(notes="initial baseline")
    assert baseline["baseline_id"].startswith("BSL@")
    assert baseline["head_seq"] == 1
    baselines = s3_archive.list_baselines()
    assert len(baselines) == 1
    assert baselines[0]["notes"] == "initial baseline"


def test_list_entries_filter(s3_archive):
    s3_archive.append("CREATE", node_id="n1")
    s3_archive.append("UPDATE", node_id="n1")
    s3_archive.append("CREATE", node_id="n2")
    creates = s3_archive.list_entries(operation="CREATE")
    assert len(creates) == 2
    since = s3_archive.list_entries(since_seq=1)
    assert len(since) == 2


def test_dek_provision_and_encrypt(s3_archive):
    s3_archive.provision_subject_key("subject-a")
    ct = s3_archive.encrypt_payload("subject-a", "secret text")
    assert ct != "secret text"
    pt = s3_archive.decrypt_payload("subject-a", ct)
    assert pt == "secret text"


def test_shred_subject(s3_archive):
    s3_archive.append("CREATE", node_id="n1")
    s3_archive.provision_subject_key("subject-b")
    result = s3_archive.shred_subject("subject-b", reason="GDPR erasure")
    assert result["subject_id"] == "subject-b"
    with pytest.raises(RuntimeError, match="shredded"):
        s3_archive.decrypt_payload("subject-b", "aa" * 24)


def test_shred_blocked_by_legal_hold(s3_archive):
    s3_archive.append("CREATE", node_id="n1")
    baseline = s3_archive.seal_baseline()
    hold_id = s3_archive.set_legal_hold(baseline["baseline_id"], reason="litigation")
    s3_archive.provision_subject_key("subject-c")
    with pytest.raises(RuntimeError, match="legal hold"):
        s3_archive.shred_subject("subject-c")
    s3_archive.release_legal_hold(hold_id)
    result = s3_archive.shred_subject("subject-c")
    assert result["subject_id"] == "subject-c"


def test_legal_hold_lifecycle(s3_archive):
    s3_archive.append("CREATE", node_id="sys")
    baseline = s3_archive.seal_baseline()
    hold_id = s3_archive.set_legal_hold(
        baseline["baseline_id"], held_by="legal@example.com", reason="regulatory"
    )
    active = s3_archive.list_legal_holds(active_only=True)
    assert len(active) == 1
    assert active[0]["hold_id"] == hold_id
    s3_archive.release_legal_hold(hold_id, released_by="legal@example.com")
    assert s3_archive.list_legal_holds(active_only=True) == []
    all_holds = s3_archive.list_legal_holds(active_only=False)
    assert len(all_holds) == 1
    assert all_holds[0]["released_at"] is not None


def test_add_timestamp_token(s3_archive):
    s3_archive.append("CREATE", node_id="n1")
    baseline = s3_archive.seal_baseline()
    s3_archive.add_timestamp_token(baseline["baseline_id"], "deadbeef")
    baselines = s3_archive.list_baselines()
    assert baselines[0]["timestamp_token_hex"] == "deadbeef"


def test_from_env_missing_bucket(monkeypatch):
    monkeypatch.delenv("ARCH_S3_BUCKET", raising=False)
    from src.infrastructure.assurance._s3_worm_archive import S3WORMAssuranceArchive

    with pytest.raises(RuntimeError, match="ARCH_S3_BUCKET"):
        S3WORMAssuranceArchive.from_env()


def test_from_env_reads_config(monkeypatch):
    monkeypatch.setenv("ARCH_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("ARCH_S3_REGION", "eu-west-1")
    monkeypatch.setenv("ARCH_S3_OBJECT_LOCK_MODE", "COMPLIANCE")
    monkeypatch.setenv("ARCH_S3_RETENTION_DAYS", "730")
    from src.infrastructure.assurance._s3_worm_archive import S3WORMAssuranceArchive

    a = S3WORMAssuranceArchive.from_env()
    assert a._bucket == "my-bucket"
    assert a._region == "eu-west-1"
    assert a._object_lock_mode == "COMPLIANCE"
    assert a._retention_days == 730
