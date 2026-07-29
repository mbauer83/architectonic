"""Shared base for cloud object-storage WORM archive adapters.

All protocol methods from AssuranceArchive and WORMAssuranceArchive are
implemented here against abstract storage primitives. Concrete subclasses
(S3WORMAssuranceArchive, AzureBlobWORMAssuranceArchive) supply those primitives.

Hash chain format mirrors SQLCipherAssuranceArchive so cross-backend offline
verification works:  SHA-256(f"{seq}|{ts}|{op}|{payload_json}|{prev_hash}")

Object layout (relative to the archive root):
  audit/{seq:012d}.json          WORM — one object per audit entry
  baselines/{id}.json            WORM — sealed baseline records
  baselines/{id}.tsa.json        WORM — RFC 3161 sidecar (add_timestamp_token)
  holds/{hold_id}.json           WORM — legal hold records
  deks/{subject_id}.json         MUTABLE — DEK store (deletable for shredding)
  _head.json                     MUTABLE — current chain head pointer
  _holds_index.json              MUTABLE — active holds index
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from src.domain.clock import epoch_seconds
from src.domain.clock import utc_now_iso as _now_iso

logger = logging.getLogger(__name__)

_AUD = "audit/"
_BAS = "baselines/"
_DEK = "deks/"
_HLD = "holds/"
_HEAD = "_head.json"
_HOLDS_IDX = "_holds_index.json"


def _compute_hash(seq: int, timestamp: str, operation: str, payload_json: str, prev_hash: str) -> str:
    raw = f"{seq}|{timestamp}|{operation}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


class _CloudWORMBase(ABC):
    """Abstract base for cloud WORM archive adapters.

    Subclasses implement the six storage primitives below; this class
    provides every AssuranceArchive and WORMAssuranceArchive method.
    """

    @abstractmethod
    def _read(self, key: str) -> dict[str, Any] | None:
        """Fetch the JSON object at key; None if absent."""

    @abstractmethod
    def _write_worm(self, key: str, data: dict[str, Any]) -> None:
        """Write an immutable object (Object Lock / container immutability policy)."""

    @abstractmethod
    def _write_mutable(self, key: str, data: dict[str, Any]) -> None:
        """Write or overwrite a mutable object (no immutability constraint)."""

    @abstractmethod
    def _delete(self, key: str) -> None:
        """Delete a mutable object. Must not be called on WORM keys."""

    @abstractmethod
    def _list_keys(self, prefix: str) -> list[str]:
        """List all WORM object keys under prefix, sorted lexicographically."""

    @abstractmethod
    def _apply_provider_legal_hold(self, *, activate: bool) -> None:
        """Activate or deactivate the cloud-native legal hold mechanism."""

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _head_data(self) -> dict[str, Any]:
        return self._read(_HEAD) or {"seq": 0, "entry_hash": ""}

    def _holds_index(self) -> dict[str, Any]:
        return self._read(_HOLDS_IDX) or {"holds": {}}

    def _has_active_holds(self) -> bool:
        return any(
            h.get("released_at") is None
            for h in self._holds_index().get("holds", {}).values()
        )

    # ── AssuranceArchive: append ──────────────────────────────────────────────

    def append(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        head = self._head_data()
        seq = int(head["seq"]) + 1
        prev_hash = str(head["entry_hash"])
        timestamp = _now_iso()
        payload_json = json.dumps(payload or {})
        entry_hash = _compute_hash(seq, timestamp, operation, payload_json, prev_hash)
        entry: dict[str, Any] = {
            "seq": seq, "timestamp": timestamp, "operation": operation,
            "node_id": node_id, "payload_json": payload_json,
            "prev_hash": prev_hash, "entry_hash": entry_hash,
        }
        self._write_worm(f"{_AUD}{seq:012d}.json", entry)
        self._write_mutable(_HEAD, {"seq": seq, "entry_hash": entry_hash})
        return {"seq": seq, "timestamp": timestamp, "operation": operation, "entry_hash": entry_hash}

    # ── AssuranceArchive: seal_baseline ───────────────────────────────────────

    def seal_baseline(
        self,
        *,
        notes: str = "",
        analysis_id: str | None = None,
    ) -> dict[str, Any]:
        head = self._head_data()
        if not head["entry_hash"]:
            raise RuntimeError("Cannot seal baseline: audit log is empty.")
        head_seq = int(head["seq"])
        head_hash = str(head["entry_hash"])
        baseline_id = f"BSL@{epoch_seconds()}.{hashlib.sha256(head_hash.encode()).hexdigest()[:8]}"
        now = _now_iso()
        record: dict[str, Any] = {
            "baseline_id": baseline_id, "created_at": now,
            "head_seq": head_seq, "head_hash": head_hash,
            "notes": notes, "analysis_id": analysis_id,
        }
        self._write_worm(f"{_BAS}{baseline_id}.json", record)
        self.append("SEAL", payload={"baseline_id": baseline_id, "head_seq": head_seq})
        return record

    # ── AssuranceArchive: verify_chain ────────────────────────────────────────

    def verify_chain(self) -> bool:
        keys = sorted(self._list_keys(_AUD))
        prev_hash = ""
        for key in keys:
            entry = self._read(key)
            if entry is None:
                return False
            expected = _compute_hash(
                int(entry["seq"]), str(entry["timestamp"]), str(entry["operation"]),
                str(entry["payload_json"]), prev_hash,
            )
            if expected != str(entry["entry_hash"]):
                logger.warning("Chain broken at seq=%s", entry.get("seq"))
                return False
            prev_hash = str(entry["entry_hash"])
        return True

    # ── AssuranceArchive: query methods ───────────────────────────────────────

    def list_entries(
        self,
        *,
        since_seq: int = 0,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for key in sorted(self._list_keys(_AUD)):
            if len(entries) >= limit:
                break
            entry = self._read(key)
            if entry is None:
                continue
            if int(entry.get("seq", 0)) <= since_seq:
                continue
            if operation and entry.get("operation") != operation:
                continue
            entries.append(entry)
        return entries

    def list_baselines(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key in sorted(self._list_keys(_BAS)):
            if key.endswith(".tsa.json"):
                continue  # sidecar — merged below
            b = self._read(key)
            if b is None:
                continue
            tsa = self._read(f"{key[:-5]}.tsa.json")
            if tsa:
                b["timestamp_token_hex"] = tsa.get("token_hex")
            result.append(b)
        return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)

    def head(self) -> dict[str, Any] | None:
        keys = sorted(self._list_keys(_AUD))
        return self._read(keys[-1]) if keys else None

    # ── WORMAssuranceArchive: DEK management ──────────────────────────────────

    def provision_subject_key(self, subject_id: str) -> str:
        key = f"{_DEK}{subject_id}.json"
        if self._read(key) is not None:
            return subject_id
        self._write_mutable(key, {
            "subject_id": subject_id, "dek_hex": os.urandom(32).hex(), "created_at": _now_iso(),
        })
        return subject_id

    def _get_dek(self, subject_id: str) -> bytes:
        row = self._read(f"{_DEK}{subject_id}.json")
        if row is None:
            raise RuntimeError(f"No DEK provisioned for subject '{subject_id}'")
        if row.get("shredded_at") is not None:
            raise RuntimeError(f"Subject '{subject_id}' has been shredded: data is permanently unrecoverable")
        return bytes.fromhex(str(row["dek_hex"]))

    def encrypt_payload(self, subject_id: str, plaintext: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
        dek = self._get_dek(subject_id)
        nonce = os.urandom(12)
        return (nonce + AESGCM(dek).encrypt(nonce, plaintext.encode(), None)).hex()

    def decrypt_payload(self, subject_id: str, ciphertext_hex: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
        dek = self._get_dek(subject_id)
        raw = bytes.fromhex(ciphertext_hex)
        return AESGCM(dek).decrypt(raw[:12], raw[12:], None).decode()

    # ── WORMAssuranceArchive: crypto-shredding ────────────────────────────────

    def shred_subject(self, subject_id: str, *, reason: str = "") -> dict[str, Any]:
        if self._has_active_holds():
            raise RuntimeError(
                "Cannot shred subject: at least one active legal hold exists. "
                "Release all holds before shredding."
            )
        key = f"{_DEK}{subject_id}.json"
        row: dict[str, Any] = self._read(key) or {}
        shredded_at = _now_iso()
        row.update({"dek_hex": "SHREDDED", "shredded_at": shredded_at})
        self._write_mutable(key, row)
        self.append("SHRED", node_id=subject_id, payload={"reason": reason, "shredded_at": shredded_at})
        return {"subject_id": subject_id, "shredded_at": shredded_at, "reason": reason}

    # ── WORMAssuranceArchive: legal holds ─────────────────────────────────────

    def set_legal_hold(self, baseline_id: str, *, held_by: str = "", reason: str = "") -> str:
        hold_id = f"HLD@{epoch_seconds()}.{os.urandom(4).hex()}"
        now = _now_iso()
        record: dict[str, Any] = {
            "hold_id": hold_id, "baseline_id": baseline_id, "held_by": held_by,
            "reason": reason, "created_at": now, "released_at": None,
        }
        self._write_worm(f"{_HLD}{hold_id}.json", record)
        idx = self._holds_index()
        idx.setdefault("holds", {})[hold_id] = record
        self._write_mutable(_HOLDS_IDX, idx)
        self._apply_provider_legal_hold(activate=True)
        self.append("LEGAL_HOLD_SET", payload={"hold_id": hold_id, "baseline_id": baseline_id})
        return hold_id

    def release_legal_hold(self, hold_id: str, *, released_by: str = "") -> None:
        idx = self._holds_index()
        if hold_id in idx.get("holds", {}):
            idx["holds"][hold_id]["released_at"] = _now_iso()
            self._write_mutable(_HOLDS_IDX, idx)
        if not self._has_active_holds():
            self._apply_provider_legal_hold(activate=False)
        self.append("LEGAL_HOLD_RELEASED", payload={"hold_id": hold_id, "released_by": released_by})

    def list_legal_holds(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        holds = list(self._holds_index().get("holds", {}).values())
        if active_only:
            holds = [h for h in holds if h.get("released_at") is None]
        return sorted(holds, key=lambda h: h.get("created_at", ""), reverse=True)

    def add_timestamp_token(self, baseline_id: str, token_der_hex: str) -> None:
        # Stored in a sidecar — baseline WORM objects cannot be modified post-write.
        self._write_worm(
            f"{_BAS}{baseline_id}.tsa.json",
            {"baseline_id": baseline_id, "token_hex": token_der_hex, "created_at": _now_iso()},
        )
