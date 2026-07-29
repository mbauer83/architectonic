"""RFC 3161 timestamp client — minimal DER-encoded request/response handling.

Builds a TimeStampReq manually (no asn1crypto / pyOpenSSL dependency) and
parses the TimeStampToken from a compliant TSA response.  Opt-in: only called
when a `tsa_url` is configured in a deployment.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

# SHA-256 AlgorithmIdentifier OID bytes (2.16.840.1.101.3.4.2.1)
_SHA256_OID_DER = bytes([0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01])
_NULL_DER = bytes([0x05, 0x00])


def _der_len(n: int) -> bytes:
    """DER length encoding (definite form)."""
    if n < 0x80:
        return bytes([n])
    length_bytes = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(length_bytes)]) + length_bytes


def _der_tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(content)) + content


def _build_timestamp_request(data_bytes: bytes) -> bytes:
    """Build a minimal RFC 3161 TimeStampReq DER structure.

    Structure:
      SEQUENCE {
        version INTEGER (1),
        messageImprint SEQUENCE {
          hashAlgorithm AlgorithmIdentifier { SHA-256 OID, NULL },
          hashedMessage OCTET STRING (32 bytes),
        },
        certReq BOOLEAN TRUE,
      }
    """
    digest = hashlib.sha256(data_bytes).digest()

    # AlgorithmIdentifier ::= SEQUENCE { algorithm OID, parameters NULL }
    alg_id = _der_tlv(0x30, _SHA256_OID_DER + _NULL_DER)

    # MessageImprint ::= SEQUENCE { hashAlgorithm AlgorithmIdentifier, hashedMessage OCTET STRING }
    hashed_msg = _der_tlv(0x04, digest)
    msg_imprint = _der_tlv(0x30, alg_id + hashed_msg)

    # version INTEGER ::= 1
    version = _der_tlv(0x02, bytes([1]))

    # certReq BOOLEAN ::= TRUE
    cert_req = _der_tlv(0x01, bytes([0xFF]))

    body = version + msg_imprint + cert_req
    return _der_tlv(0x30, body)


def _read_der_length(buf: bytes, offset: int) -> tuple[int, int]:
    """Decode a DER definite-form length at *offset*; return (length, header byte count)."""
    first = buf[offset]
    if first & 0x80:
        n = first & 0x7F
        return int.from_bytes(buf[offset + 1 : offset + 1 + n], "big"), 1 + n
    return first, 1


def _check_pki_status(buf: bytes, status_offset: int) -> None:
    """Reject a TSA response whose PKIStatus is neither granted (0) nor grantedWithMods (1)."""
    if buf[status_offset] != 0x02:
        return
    if buf[status_offset + 1] != 1:
        raise RuntimeError("Unexpected PKIStatus INTEGER encoding in TSA response")
    status_val = buf[status_offset + 2]
    if status_val not in (0, 1):
        raise RuntimeError(f"TSA returned non-zero status: {status_val}")


def _parse_timestamp_response(resp_bytes: bytes) -> bytes:
    """Extract the timeStampToken from a RFC 3161 TimeStampResp DER response.

    TimeStampResp ::= SEQUENCE { status PKIStatusInfo, timeStampToken ContentInfo OPTIONAL }
    PKIStatusInfo ::= SEQUENCE { status PKIStatus, ... }
    PKIStatus 0 = granted, 1 = grantedWithMods.
    """
    if not resp_bytes or resp_bytes[0] != 0x30:
        raise RuntimeError("Invalid TSA response: expected SEQUENCE tag")

    _, outer_header_len = _read_der_length(resp_bytes, 1)
    offset = 1 + outer_header_len  # start of PKIStatusInfo

    if resp_bytes[offset] != 0x30:
        raise RuntimeError("Invalid TSA response: expected PKIStatusInfo SEQUENCE")
    pki_offset = offset + 1
    pki_len, pki_header_len = _read_der_length(resp_bytes, pki_offset)
    _check_pki_status(resp_bytes, pki_offset + pki_header_len)

    token_start = offset + 1 + pki_header_len + pki_len
    if token_start >= len(resp_bytes):
        raise RuntimeError("TSA response contains no timeStampToken")
    return resp_bytes[token_start:]


def request_timestamp(data: bytes, *, tsa_url: str) -> bytes:
    """POST a RFC 3161 timestamp request to the TSA and return the DER token."""
    import httpx  # type: ignore[import-untyped]  # noqa: PLC0415

    req_der = _build_timestamp_request(data)
    resp = httpx.post(
        tsa_url,
        content=req_der,
        headers={"Content-Type": "application/timestamp-query"},
        timeout=30,
    )
    resp.raise_for_status()
    logger.info("TSA response: %s bytes from %s", len(resp.content), tsa_url)
    return _parse_timestamp_response(resp.content)


def format_token_for_log(token_der: bytes) -> str:
    return token_der.hex()
