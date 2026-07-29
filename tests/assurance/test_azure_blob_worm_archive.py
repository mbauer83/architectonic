"""Unit tests for AzureBlobWORMAssuranceArchive using unittest.mock.

Azure SDK is optional; tests are skipped when it is absent.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

azure_blob = pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")


def _make_archive(store: dict | None = None, worm: dict | None = None):
    """Return an AzureBlobWORMAssuranceArchive backed by two dict-stores (mock)."""
    from src.infrastructure.assurance._azure_blob_worm_archive import AzureBlobWORMAssuranceArchive

    mutable_store: dict[str, bytes] = {}
    worm_store: dict[str, bytes] = worm or {}

    def _make_blob_client(container_store: dict, key: str) -> MagicMock:
        bc = MagicMock()

        def _download():
            dl = MagicMock()
            if key not in container_store:
                from azure.core.exceptions import ResourceNotFoundError

                raise ResourceNotFoundError
            dl.readall.return_value = container_store[key]
            return dl

        def _upload(data, overwrite=True, content_settings=None):
            if not overwrite and key in container_store:
                from azure.core.exceptions import ResourceExistsError

                raise ResourceExistsError
            container_store[key] = data

        bc.download_blob.side_effect = _download
        bc.upload_blob.side_effect = _upload
        bc.delete_blob.side_effect = lambda: container_store.pop(key, None)
        return bc

    def _make_container_client(container_store: dict) -> MagicMock:
        cc = MagicMock()

        def _get_blob_client(key):
            return _make_blob_client(container_store, key)

        cc.get_blob_client.side_effect = _get_blob_client

        def _list_blobs(name_starts_with=""):
            for k in sorted(container_store):
                if k.startswith(name_starts_with):
                    m = MagicMock()
                    m.name = k
                    yield m

        cc.list_blobs.side_effect = _list_blobs
        cc.set_legal_hold.return_value = None
        return cc

    archive = AzureBlobWORMAssuranceArchive.__new__(AzureBlobWORMAssuranceArchive)
    archive._account_name = "testaccount"
    archive._container = "archive"
    archive._state_container = "archive-state"
    archive._account_key = "key"
    archive._immutability_days = 365
    archive._worm_client = _make_container_client(worm_store)
    archive._state_client = _make_container_client(mutable_store)
    return archive


def test_append_and_verify():
    a = _make_archive()
    a.append("CREATE", node_id="n1")
    a.append("UPDATE", node_id="n1")
    assert a.verify_chain() is True
    assert a.head()["seq"] == 2  # type: ignore[index]


def test_seal_baseline():
    a = _make_archive()
    a.append("CREATE", node_id="sys")
    b = a.seal_baseline(notes="first baseline")
    assert b["baseline_id"].startswith("BSL@")
    assert len(a.list_baselines()) == 1


def test_dek_provision_encrypt_decrypt():
    a = _make_archive()
    a.provision_subject_key("subject-x")
    ct = a.encrypt_payload("subject-x", "hello world")
    assert a.decrypt_payload("subject-x", ct) == "hello world"


def test_shred_destroys_dek():
    a = _make_archive()
    a.append("CREATE", node_id="n1")
    a.provision_subject_key("s1")
    a.shred_subject("s1")
    with pytest.raises(RuntimeError, match="shredded"):
        a._get_dek("s1")


def test_legal_hold_blocks_shred():
    a = _make_archive()
    a.append("CREATE", node_id="n1")
    baseline = a.seal_baseline()
    hold_id = a.set_legal_hold(baseline["baseline_id"])
    a.provision_subject_key("s2")
    with pytest.raises(RuntimeError, match="legal hold"):
        a.shred_subject("s2")
    a.release_legal_hold(hold_id)
    a.shred_subject("s2")  # now succeeds


def test_timestamp_sidecar():
    a = _make_archive()
    a.append("CREATE", node_id="n1")
    b = a.seal_baseline()
    a.add_timestamp_token(b["baseline_id"], "cafebabe")
    baselines = a.list_baselines()
    assert baselines[0]["timestamp_token_hex"] == "cafebabe"


def test_from_env_missing_account(monkeypatch):
    monkeypatch.delenv("ARCH_AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("ARCH_AZURE_CONTAINER", raising=False)
    from src.infrastructure.assurance._azure_blob_worm_archive import (
        AzureBlobWORMAssuranceArchive,
    )

    with pytest.raises(RuntimeError, match="ARCH_AZURE_STORAGE_ACCOUNT"):
        AzureBlobWORMAssuranceArchive.from_env()


def test_from_env_reads_config(monkeypatch):
    monkeypatch.setenv("ARCH_AZURE_STORAGE_ACCOUNT", "myaccount")
    monkeypatch.setenv("ARCH_AZURE_CONTAINER", "mycontainer")
    monkeypatch.setenv("ARCH_AZURE_STATE_CONTAINER", "mycontainer-idx")
    monkeypatch.setenv("ARCH_AZURE_IMMUTABILITY_DAYS", "730")
    from src.infrastructure.assurance._azure_blob_worm_archive import (
        AzureBlobWORMAssuranceArchive,
    )

    a = AzureBlobWORMAssuranceArchive.from_env()
    assert a._account_name == "myaccount"
    assert a._container == "mycontainer"
    assert a._state_container == "mycontainer-idx"
    assert a._immutability_days == 730
