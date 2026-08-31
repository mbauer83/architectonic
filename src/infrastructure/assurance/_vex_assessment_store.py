"""SQLCipher/SQLite adapter for contextual VEX assessments.

VEX is run-independent: the key is (anchor, canonical component incl. version,
canonical vulnerability). Revisions are immutable and append-only; each write
lands its hash-chained audit row in the SAME transaction (the audited-mutation
durability invariant).
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._archive import append_audit_row
from src.infrastructure.assurance._signals_migrations import (
    apply_signals_migrations,
    apply_signals_pragmas,
)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return f"{prefix}@{digest}"


class SQLCipherVexAssessmentStore:
    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._conn_factory = conn_factory

    def _conn(self) -> Any:
        conn = self._conn_factory()
        if conn is None:
            raise RuntimeError("Assurance store is locked — cannot access VEX assessments.")
        apply_signals_pragmas(conn)
        apply_signals_migrations(conn)
        return conn

    def _begin(self, conn: Any) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:  # noqa: BLE001 — an implicit transaction is already open
            pass

    def record_vex_assessment(
        self,
        *,
        anchor_entity_id: str,
        canonical_component_id: str,
        canonical_vulnerability_id: str,
        vex_status: str,
        justification: str,
        author: str,
        source: str = "",
    ) -> dict[str, Any]:
        """Append one immutable VEX revision for the run-independent key —
        revision number allocation, the row, and its audit record commit in
        ONE transaction."""
        conn = self._conn()
        self._begin(conn)
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS next_rev FROM vex_assessments "
                "WHERE anchor_entity_id=? AND canonical_component_id=? AND canonical_vulnerability_id=?",
                (anchor_entity_id, canonical_component_id, canonical_vulnerability_id),
            ).fetchone()
            revision = int(row["next_rev"])
            assessment_id = _stable_id(
                "VEX", anchor_entity_id, canonical_component_id,
                canonical_vulnerability_id, str(revision),
            )
            created_at = _now_iso()
            conn.execute(
                "INSERT INTO vex_assessments "
                "(assessment_id, anchor_entity_id, canonical_component_id, "
                "canonical_vulnerability_id, revision, vex_status, justification, "
                "author, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (assessment_id, anchor_entity_id, canonical_component_id,
                 canonical_vulnerability_id, revision, vex_status, justification,
                 author, source, created_at),
            )
            append_audit_row(conn, "VEX_ASSESSMENT_RECORDED", payload={
                "assessment_id": assessment_id,
                "anchor_entity_id": anchor_entity_id,
                "canonical_component_id": canonical_component_id,
                "canonical_vulnerability_id": canonical_vulnerability_id,
                "revision": revision,
                "vex_status": vex_status,
            })
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {"assessment_id": assessment_id, "revision": revision, "created_at": created_at}

    def list_vex_revisions(
        self,
        *,
        anchor_entity_id: str,
        canonical_component_id: str,
        canonical_vulnerability_id: str,
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        return conn.execute(
            "SELECT * FROM vex_assessments WHERE anchor_entity_id=? AND "
            "canonical_component_id=? AND canonical_vulnerability_id=? ORDER BY revision",
            (anchor_entity_id, canonical_component_id, canonical_vulnerability_id),
        ).fetchall()

    def list_anchor_assessments(self, anchor_entity_id: str) -> list[dict[str, Any]]:
        """Every revision for the anchor — callers pick current revisions per
        key AFTER exposure filtering (visibility before suppression)."""
        conn = self._conn()
        return conn.execute(
            "SELECT * FROM vex_assessments WHERE anchor_entity_id=? ORDER BY revision",
            (anchor_entity_id,),
        ).fetchall()
