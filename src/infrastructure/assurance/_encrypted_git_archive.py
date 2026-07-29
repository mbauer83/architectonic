"""Encrypted JSONL-backed append-only audit log for the private-git assurance store.

Separates tamper-evidence from confidentiality:
  - chain.jsonl  — unencrypted manifest: {seq, timestamp, operation, entry_hash, prev_hash}
                   readable without the Fernet key; enables O(n) chain continuity check.
  - {seq:08d}.enc — Fernet-encrypted full entry (includes payload_json and node_id).
  - baselines/{id}.enc — Fernet-encrypted baseline JSON.

Hash formula (identical to _archive._compute_hash):
  SHA256(f"{seq}|{timestamp}|{operation}|{payload_json}|{prev_hash}")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, TypedDict

from src.domain.clock import epoch_seconds
from src.domain.clock import utc_now_iso as _now_iso

logger = logging.getLogger(__name__)


class _ManifestRow(TypedDict):
    seq: int
    timestamp: str
    operation: str
    entry_hash: str
    prev_hash: str


def _compute_hash(
    seq: int,
    timestamp: str,
    operation: str,
    payload_json: str,
    prev_hash: str,
) -> str:
    raw = f"{seq}|{timestamp}|{operation}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


class EncryptedGitArchive:
    """AssuranceArchive adapter for the private-git backend.

    Fernet key is obtained via fernet_factory each call — returning None means
    the store is locked, and all methods raise RuntimeError.
    """

    def __init__(self, repo_path: Path, fernet_factory: Callable[[], Any]) -> None:
        self._repo = repo_path
        self._log_dir = repo_path / "log"
        self._chain_path = repo_path / "log" / "chain.jsonl"
        self._baselines_dir = repo_path / "log" / "baselines"
        self._fernet_factory = fernet_factory

    # ── Lock guard ────────────────────────────────────────────────────────────

    def _require_unlocked(self) -> Any:
        fernet = self._fernet_factory()
        if fernet is None:
            raise RuntimeError("Encrypted archive is locked — call store unlock() first.")
        return fernet

    # ── Encrypted I/O ─────────────────────────────────────────────────────────

    def _write_enc(self, path: Path, data: dict[str, object]) -> None:
        fernet = self._require_unlocked()
        plaintext = json.dumps(data).encode()
        ciphertext = fernet.encrypt(plaintext)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(ciphertext)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read_enc(self, path: Path) -> dict[str, object] | None:
        fernet = self._require_unlocked()
        if not path.exists():
            return None
        try:
            plaintext = fernet.decrypt(path.read_bytes())
            return json.loads(plaintext)  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            logger.warning("Decrypt failed for %s — skipping (wrong key?)", path)
            return None

    def _read_chain(self) -> list[_ManifestRow]:
        if not self._chain_path.exists():
            return []
        rows: list[_ManifestRow] = []
        for line in self._chain_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Corrupt chain.jsonl line: %r", line)
        return rows

    # ── Append ────────────────────────────────────────────────────────────────

    def append(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._read_chain()
        if manifest:
            last = manifest[-1]
            prev_hash = last["entry_hash"]
            seq = last["seq"] + 1
        else:
            prev_hash = ""
            seq = 1

        timestamp = _now_iso()
        payload_json = json.dumps(payload or {})
        entry_hash = _compute_hash(seq, timestamp, operation, payload_json, prev_hash)

        full_entry: dict[str, object] = {
            "seq": seq,
            "timestamp": timestamp,
            "operation": operation,
            "node_id": node_id,
            "payload_json": payload_json,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
        }
        self._write_enc(self._log_dir / f"{seq:08d}.enc", full_entry)

        manifest_entry = {
            "seq": seq,
            "timestamp": timestamp,
            "operation": operation,
            "entry_hash": entry_hash,
            "prev_hash": prev_hash,
        }
        with self._chain_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest_entry) + "\n")

        return {"seq": seq, "timestamp": timestamp, "operation": operation, "entry_hash": entry_hash}

    # ── Seal baseline ─────────────────────────────────────────────────────────

    def seal_baseline(
        self,
        *,
        notes: str = "",
        analysis_id: str | None = None,
    ) -> dict[str, object]:
        self._require_unlocked()
        manifest = self._read_chain()
        if not manifest:
            raise RuntimeError("Cannot seal baseline: audit log is empty.")

        last = manifest[-1]
        head_seq = last["seq"]
        head_hash = last["entry_hash"]

        baseline_id = f"BSL@{epoch_seconds()}.{hashlib.sha256(head_hash.encode()).hexdigest()[:8]}"
        now = _now_iso()
        self._baselines_dir.mkdir(parents=True, exist_ok=True)

        baseline_data: dict[str, object] = {
            "baseline_id": baseline_id,
            "created_at": now,
            "head_seq": head_seq,
            "head_hash": head_hash,
            "notes": notes,
            "analysis_id": analysis_id,
        }
        self._write_enc(self._baselines_dir / f"{baseline_id}.enc", baseline_data)
        self.append("SEAL", payload={"baseline_id": baseline_id, "head_seq": head_seq})

        return {
            "baseline_id": baseline_id,
            "created_at": now,
            "head_seq": head_seq,
            "head_hash": head_hash,
        }

    # ── Verification ─────────────────────────────────────────────────────────

    def verify_chain(self) -> bool:
        self._require_unlocked()
        manifest = self._read_chain()
        if not manifest:
            return True
        prev_hash = ""
        for row in manifest:
            if not row["entry_hash"]:
                return False
            if row["prev_hash"] != prev_hash:
                logger.error("Chain break at seq=%s", row["seq"])
                return False
            prev_hash = row["entry_hash"]
        return True

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_entries(
        self,
        *,
        since_seq: int = 0,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        manifest = self._read_chain()
        results: list[dict[str, object]] = []
        for row in manifest:
            if row["seq"] <= since_seq:
                continue
            entry = self._read_enc(self._log_dir / f"{row['seq']:08d}.enc")
            if entry is None:
                continue
            if operation and entry.get("operation") != operation:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def list_baselines(self) -> list[dict[str, object]]:
        self._require_unlocked()
        if not self._baselines_dir.exists():
            return []
        results: list[dict[str, object]] = []
        for path in sorted(self._baselines_dir.glob("*.enc")):
            item = self._read_enc(path)
            if item is not None:
                results.append(item)
        return sorted(results, key=lambda b: str(b.get("created_at", "")), reverse=True)

    def head(self) -> dict[str, object] | None:
        self._require_unlocked()
        manifest = self._read_chain()
        if not manifest:
            return None
        last = manifest[-1]
        return self._read_enc(self._log_dir / f"{last['seq']:08d}.enc")
