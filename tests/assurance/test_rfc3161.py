"""Tests for the RFC 3161 timestamp client."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch


def test_build_timestamp_request_starts_with_sequence_tag() -> None:
    from src.infrastructure.assurance._rfc3161 import _build_timestamp_request  # noqa: PLC0415

    req = _build_timestamp_request(b"hello world")

    assert req[0] == 0x30, "Outer structure must be a SEQUENCE (tag 0x30)"
    assert len(req) > 20


def test_build_timestamp_request_contains_sha256_oid() -> None:
    from src.infrastructure.assurance._rfc3161 import _build_timestamp_request  # noqa: PLC0415

    req = _build_timestamp_request(b"test data")

    # SHA-256 OID: 2.16.840.1.101.3.4.2.1
    sha256_oid = bytes([0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01])
    assert sha256_oid in req


def test_build_timestamp_request_contains_hash_of_input() -> None:
    from src.infrastructure.assurance._rfc3161 import _build_timestamp_request  # noqa: PLC0415

    data = b"some analysis fingerprint"
    req = _build_timestamp_request(data)

    digest = hashlib.sha256(data).digest()
    assert digest in req


def test_der_len_single_byte() -> None:
    from src.infrastructure.assurance._rfc3161 import _der_len  # noqa: PLC0415

    assert _der_len(0) == bytes([0])
    assert _der_len(127) == bytes([127])


def test_der_len_multi_byte() -> None:
    from src.infrastructure.assurance._rfc3161 import _der_len  # noqa: PLC0415

    result = _der_len(256)
    assert result[0] == 0x82  # 0x80 | 2 length bytes
    assert int.from_bytes(result[1:], "big") == 256


def test_format_token_for_log_returns_hex() -> None:
    from src.infrastructure.assurance._rfc3161 import format_token_for_log  # noqa: PLC0415

    token = bytes([0x30, 0x01, 0xFF])
    result = format_token_for_log(token)

    assert result == "3001ff"
    assert all(c in "0123456789abcdef" for c in result)


@patch("httpx.post")
def test_request_timestamp_posts_correct_content_type(mock_post) -> None:
    from src.infrastructure.assurance._rfc3161 import request_timestamp  # noqa: PLC0415

    # Build a minimal valid TSA response: outer SEQUENCE, PKIStatusInfo (SEQUENCE with INTEGER 0), token
    pki_status_int = bytes([0x02, 0x01, 0x00])  # INTEGER 0 = granted
    pki_status_info = bytes([0x30]) + bytes([len(pki_status_int)]) + pki_status_int
    token_bytes = bytes([0x30, 0x02, 0x05, 0x00])  # placeholder ContentInfo
    body = pki_status_info + token_bytes
    outer = bytes([0x30]) + bytes([len(body)]) + body

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = outer
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    request_timestamp(b"data", tsa_url="http://tsa.example.com/tsr")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"]["Content-Type"] == "application/timestamp-query"


@patch("httpx.post")
def test_request_timestamp_returns_token_bytes(mock_post) -> None:
    from src.infrastructure.assurance._rfc3161 import request_timestamp  # noqa: PLC0415

    pki_status_int = bytes([0x02, 0x01, 0x00])
    pki_status_info = bytes([0x30]) + bytes([len(pki_status_int)]) + pki_status_int
    token_bytes = bytes([0x30, 0x03, 0xAA, 0xBB, 0xCC])
    body = pki_status_info + token_bytes
    outer = bytes([0x30]) + bytes([len(body)]) + body

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = outer
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    token = request_timestamp(b"payload", tsa_url="http://tsa.example.com/tsr")

    assert token == token_bytes
