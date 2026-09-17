"""Bytes that arrived some other way are judged by the same refusal as a download.

The release updater fetches an asset through an API client and holds the bytes; `verify_bytes` is how
it asks the same question `download_verified` asks, so a stated digest and a pinned one are checked by
one comparison. The mismatch names the source and both digests, and a matching pair passes silently.
"""

from __future__ import annotations

import hashlib

import pytest

from src.infrastructure.bootstrap import asset_download
from src.infrastructure.bootstrap.asset_download import download_verified, verify_bytes

_PAYLOAD = b"published bytes"
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()


def test_matching_bytes_pass_silently() -> None:
    assert verify_bytes(_PAYLOAD, expected_sha256=_DIGEST.upper(), source="architectonic-gui.tar.gz") is None


def test_a_mismatch_names_the_source_and_both_digests() -> None:
    with pytest.raises(SystemExit) as refusal:
        verify_bytes(b"tampered", expected_sha256=_DIGEST, source="architectonic-gui.tar.gz")
    message = str(refusal.value)
    assert "architectonic-gui.tar.gz" in message
    assert _DIGEST in message
    assert hashlib.sha256(b"tampered").hexdigest() in message


def test_download_verified_is_the_same_refusal_over_a_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    """A mismatch writes nothing: the caller never receives bytes to write."""
    monkeypatch.setattr(asset_download, "download_bytes", lambda url, *, label=None: b"tampered")
    target = tmp_path / "asset.bin"
    with pytest.raises(SystemExit):
        target.write_bytes(download_verified("https://example.invalid/asset", expected_sha256=_DIGEST))
    assert not target.exists()
