"""WORM-capable archive with per-subject envelope encryption, legal-hold, and crypto-shredding.

Extends SQLCipherAssuranceArchive with:
- Per-subject AES-256-GCM DEK provisioning and envelope encryption
- Legal-hold registry (prevents shredding while hold is active)
- Crypto-shred: destroys the DEK, making encrypted payloads permanently unrecoverable
  without deleting the record shell (satisfies WORM/immutable-store constraints)
- RFC 3161 timestamp token attachment to sealed baselines (opt-in)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from src.domain.clock import epoch_seconds
from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive

logger = logging.getLogger(__name__)


def _hold_id() -> str:
    rand = os.urandom(6).hex()
    return f"HLD@{epoch_seconds()}.{rand}"


class WORMSQLCipherAssuranceArchive(SQLCipherAssuranceArchive):
    """Adds WORM governance depth to the SQLCipher archive.

    The base archive's records remain append-only. This extension adds:
    - Envelope encryption (per-subject DEK in dek_store)
    - Legal holds (legal_holds table)
    - Crypto-shredding (set shredded_at, clear DEK)
    - RFC 3161 timestamp tokens on baselines
    """

    # ── DEK management ────────────────────────────────────────────────────────

    def provision_subject_key(self, subject_id: str) -> str:
        """Generate and store a 256-bit AES key for subject_id. Idempotent."""
        conn = self._conn()
        existing = conn.execute(
            "SELECT subject_id FROM dek_store WHERE subject_id = ?", (subject_id,)
        ).fetchone()
        if existing:
            return subject_id
        dek = os.urandom(32)
        conn.execute(
            "INSERT INTO dek_store (subject_id, dek_hex, created_at) VALUES (?, ?, ?)",
            (subject_id, dek.hex(), _now_iso()),
        )
        conn.commit()
        return subject_id

    def _get_dek(self, subject_id: str) -> bytes:
        conn = self._conn()
        row = conn.execute(
            "SELECT dek_hex, shredded_at FROM dek_store WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"No DEK provisioned for subject '{subject_id}'")
        if row["shredded_at"] is not None:
            raise RuntimeError(f"Subject '{subject_id}' has been shredded: data permanently unrecoverable")
        return bytes.fromhex(str(row["dek_hex"]))

    def encrypt_payload(self, subject_id: str, plaintext: str) -> str:
        """AES-256-GCM encrypt plaintext under subject's DEK. Returns hex(nonce+ct+tag)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

        dek = self._get_dek(subject_id)
        nonce = os.urandom(12)
        aesgcm = AESGCM(dek)
        ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return (nonce + ct_with_tag).hex()

    def decrypt_payload(self, subject_id: str, ciphertext_hex: str) -> str:
        """Decrypt a payload encrypted with encrypt_payload. Raises if subject was shredded."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

        dek = self._get_dek(subject_id)
        raw = bytes.fromhex(ciphertext_hex)
        nonce, ct_with_tag = raw[:12], raw[12:]
        aesgcm = AESGCM(dek)
        return aesgcm.decrypt(nonce, ct_with_tag, None).decode()

    # ── Crypto-shredding ──────────────────────────────────────────────────────

    def shred_subject(self, subject_id: str, *, reason: str = "") -> dict[str, object]:
        """Destroy the DEK for subject_id, making all encrypted payloads unrecoverable.

        Blocked while any active legal hold exists (conservative: protects the entire archive).
        """
        conn = self._conn()
        hold_count: dict[str, Any] = conn.execute(
            "SELECT COUNT(*) AS cnt FROM legal_holds WHERE released_at IS NULL"
        ).fetchone()
        if int(hold_count["cnt"]) > 0:
            raise RuntimeError(
                "Cannot shred subject: at least one active legal hold exists. "
                "Release all holds before shredding."
            )
        now = _now_iso()
        conn.execute(
            "UPDATE dek_store SET dek_hex = 'SHREDDED', shredded_at = ? WHERE subject_id = ?",
            (now, subject_id),
        )
        conn.commit()
        self.append("SHRED", node_id=subject_id, payload={"reason": reason, "shredded_at": now})
        return {"subject_id": subject_id, "shredded_at": now, "reason": reason}

    # ── Legal holds ───────────────────────────────────────────────────────────

    def set_legal_hold(self, baseline_id: str, *, held_by: str = "", reason: str = "") -> str:
        conn = self._conn()
        hold_id = _hold_id()
        conn.execute(
            "INSERT INTO legal_holds (hold_id, baseline_id, held_by, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (hold_id, baseline_id, held_by, reason, _now_iso()),
        )
        conn.commit()
        self.append("LEGAL_HOLD_SET", payload={"hold_id": hold_id, "baseline_id": baseline_id})
        return hold_id

    def release_legal_hold(self, hold_id: str, *, released_by: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE legal_holds SET released_at = ? WHERE hold_id = ?",
            (_now_iso(), hold_id),
        )
        conn.commit()
        self.append("LEGAL_HOLD_RELEASED", payload={"hold_id": hold_id, "released_by": released_by})

    def list_legal_holds(self, *, active_only: bool = True) -> list[dict[str, object]]:
        conn = self._conn()
        sql = "SELECT * FROM legal_holds"
        if active_only:
            sql += " WHERE released_at IS NULL"
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    # ── Timestamp tokens ──────────────────────────────────────────────────────

    def add_timestamp_token(self, baseline_id: str, token_der_hex: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE baselines SET timestamp_token_hex = ? WHERE baseline_id = ?",
            (token_der_hex, baseline_id),
        )
        conn.commit()

    # ── seal_baseline override ────────────────────────────────────────────────

    def seal_baseline(
        self,
        *,
        notes: str = "",
        analysis_id: str | None = None,
        tsa_url: str | None = None,
    ) -> dict[str, object]:
        """Seal baseline; optionally attach a RFC 3161 timestamp token."""
        result = super().seal_baseline(notes=notes, analysis_id=analysis_id)
        if tsa_url:
            from src.infrastructure.assurance._rfc3161 import format_token_for_log, request_timestamp  # noqa: PLC0415

            fingerprint = hashlib.sha256(str(result["head_hash"]).encode()).digest()
            token_der = request_timestamp(fingerprint, tsa_url=tsa_url)
            token_hex = format_token_for_log(token_der)
            self.add_timestamp_token(str(result["baseline_id"]), token_hex)
            result = {**result, "timestamp_token_hex": token_hex}
        return result
