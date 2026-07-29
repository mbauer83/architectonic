"""Append-only hash-chained audit log — the AssuranceArchive adapter.

Implements EU AI Act Art. 12 logging capability with tamper-evident hash chain.
The archive uses a separate table in the same SQLCipher store as the live data
(same DB file, same key), ensuring consistent encryption.

Hash chain: each entry's `entry_hash` = SHA-256 of:
    seq || timestamp || operation || payload_json || prev_hash
This makes any tampering with past entries detectable on chain verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from src.domain.clock import epoch_seconds
from src.domain.clock import utc_now_iso as _now_iso

logger = logging.getLogger(__name__)


def _compute_hash(
    seq: int,
    timestamp: str,
    operation: str,
    payload_json: str,
    prev_hash: str,
) -> str:
    raw = f"{seq}|{timestamp}|{operation}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def append_audit_row(
    conn: Any,
    operation: str,
    *,
    node_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """Append one hash-chained audit row WITHOUT committing — for callers that
    must land the audit record in the same transaction as the signal mutation
    it describes (the audited-mutation durability invariant). The plain
    ``append`` method wraps this with its own commit."""
    timestamp = _now_iso()
    payload_json = json.dumps(payload or {})
    head = conn.execute(
        "SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_hash = head["entry_hash"] if head else ""
    seq_row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM audit_log"
    ).fetchone()
    seq = int(seq_row["next_seq"])
    entry_hash = _compute_hash(seq, timestamp, operation, payload_json, prev_hash)
    conn.execute(
        "INSERT INTO audit_log (seq, timestamp, operation, node_id, payload_json, prev_hash, entry_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (seq, timestamp, operation, node_id, payload_json, prev_hash, entry_hash),
    )
    return {"seq": seq, "timestamp": timestamp, "operation": operation, "entry_hash": entry_hash}


class SQLCipherAssuranceArchive:
    """Adapter implementing AssuranceArchive backed by the assurance SQLCipher store.

    The archive shares the DB connection from SQLCipherAssuranceStore.
    Pass the store's internal _conn reference or use the factory.
    """

    def __init__(self, conn_factory: Any) -> None:
        self._conn_factory = conn_factory

    def _conn(self) -> Any:
        c = self._conn_factory()
        if c is None:
            raise RuntimeError("Assurance store is locked — cannot access archive.")
        return c

    # ── Append ────────────────────────────────────────────────────────────────

    def append(
        self,
        operation: str,
        *,
        node_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        conn = self._conn()
        entry = append_audit_row(conn, operation, node_id=node_id, payload=payload)
        conn.commit()
        return entry

    # ── Seal baseline ─────────────────────────────────────────────────────────

    def seal_baseline(
        self,
        *,
        notes: str = "",
        analysis_id: str | None = None,
    ) -> dict[str, object]:
        conn = self._conn()
        head = conn.execute(
            "SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if head is None:
            raise RuntimeError("Cannot seal baseline: audit log is empty.")
        head_seq = int(head["seq"])
        head_hash = str(head["entry_hash"])

        baseline_id = f"BSL@{epoch_seconds()}.{hashlib.sha256(head_hash.encode()).hexdigest()[:8]}"
        now = _now_iso()
        conn.execute(
            "INSERT INTO baselines (baseline_id, created_at, head_seq, head_hash, notes, analysis_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (baseline_id, now, head_seq, head_hash, notes, analysis_id),
        )
        conn.commit()
        self.append("SEAL", payload={"baseline_id": baseline_id, "head_seq": head_seq})
        return {
            "baseline_id": baseline_id,
            "created_at": now,
            "head_seq": head_seq,
            "head_hash": head_hash,
        }

    # ── Verification ─────────────────────────────────────────────────────────

    def verify_chain(self) -> bool:
        conn = self._conn()
        rows = conn.execute(
            "SELECT seq, timestamp, operation, payload_json, prev_hash, entry_hash "
            "FROM audit_log ORDER BY seq"
        ).fetchall()
        prev_hash = ""
        for row in rows:
            expected = _compute_hash(
                int(row["seq"]),
                str(row["timestamp"]),
                str(row["operation"]),
                str(row["payload_json"]),
                prev_hash,
            )
            if expected != str(row["entry_hash"]):
                logger.error("Chain verification failed at seq=%s", row["seq"])
                return False
            prev_hash = str(row["entry_hash"])
        return True

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_entries(
        self,
        *,
        since_seq: int = 0,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        conn = self._conn()
        clauses = ["seq > ?"]
        params: list[object] = [since_seq]
        if operation:
            clauses.append("operation = ?")
            params.append(operation)
        where = f"WHERE {' AND '.join(clauses)}"
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY seq LIMIT ?", params
        ).fetchall()
        return [dict(r) for r in rows]

    def list_baselines(self) -> list[dict[str, object]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM baselines ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def head(self) -> dict[str, object] | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
