"""The digest check is the only thing between a provisioning step and a compromised mirror.

Every provisioning command in `src/infrastructure/bootstrap/` acquires something this repository
deliberately does not carry, and each of them decides whether to trust the bytes by comparing a
SHA-256 against a pinned constant. That comparison used to be written once per command; these
tests state it once, over the module all three now call, so a caller cannot quietly acquire a
weaker version of it.
"""

from __future__ import annotations

import hashlib

import pytest

from src.infrastructure.bootstrap import asset_download
from src.infrastructure.bootstrap.asset_download import download_verified, sha256_hex

_PAYLOAD = b"the bytes a mirror served"
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()


def _serving(payload: bytes) -> object:
    """A stand-in for the network that records the URL and label it was asked for."""

    calls: list[tuple[str, str | None]] = []

    def download_bytes(url: str, *, label: str | None = None) -> bytes:
        calls.append((url, label))
        return payload

    download_bytes.calls = calls  # type: ignore[attr-defined]
    return download_bytes


def test_matching_digest_returns_the_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asset_download, "download_bytes", _serving(_PAYLOAD))
    assert download_verified("https://example.invalid/asset", expected_sha256=_DIGEST) == _PAYLOAD


def test_the_pinned_digest_is_compared_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    """A digest pasted from a sidecar or a release page may arrive uppercase."""
    monkeypatch.setattr(asset_download, "download_bytes", _serving(_PAYLOAD))
    assert download_verified("https://example.invalid/asset", expected_sha256=_DIGEST.upper()) == _PAYLOAD


def test_a_mismatch_refuses_and_names_both_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller gets nothing back, so it has nothing to install."""
    monkeypatch.setattr(asset_download, "download_bytes", _serving(b"something else entirely"))
    with pytest.raises(SystemExit) as refusal:
        download_verified("https://example.invalid/asset", expected_sha256=_DIGEST)
    message = str(refusal.value)
    assert _DIGEST in message
    assert sha256_hex(b"something else entirely") in message
    assert "https://example.invalid/asset" in message


def test_an_empty_expected_digest_is_a_mismatch_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pin that was never filled in must fail closed rather than accept anything."""
    monkeypatch.setattr(asset_download, "download_bytes", _serving(_PAYLOAD))
    with pytest.raises(SystemExit):
        download_verified("https://example.invalid/asset", expected_sha256="")


def test_the_label_is_passed_through_so_a_download_can_narrate_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    serving = _serving(_PAYLOAD)
    monkeypatch.setattr(asset_download, "download_bytes", serving)
    download_verified("https://example.invalid/asset", expected_sha256=_DIGEST, label="weights")
    assert serving.calls == [("https://example.invalid/asset", "weights")]  # type: ignore[attr-defined]


def test_sha256_hex_is_lowercase_hex() -> None:
    digest = sha256_hex(_PAYLOAD)
    assert digest == digest.lower()
    assert digest == _DIGEST
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_sha256_hex_agrees_with_hashlib_on_a_known_value() -> None:
    """Carried over from the two per-command copies this module replaced."""
    assert sha256_hex(b"") == hashlib.sha256(b"").hexdigest()
