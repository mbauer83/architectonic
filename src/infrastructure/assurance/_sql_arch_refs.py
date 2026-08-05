"""The architecture cross-reference rows of a SQL-backed assurance store.

Its own module for the same reason the FMEA assessment methods have one: the store is one adapter with
several concerns, and the file limit is what keeps them from accreting in one place. What lives here is
only the SQL — which refs a rename speaks about is a domain rule
(`src/domain/assurance/arch_ref_identity.py`), shared with the file- and PocketBase-backed stores.
"""

from __future__ import annotations

from typing import Any

from src.domain.assurance.arch_ref_identity import refs_to_retarget

from ._edge_records import as_arch_ref_records
from ._sqlcipher_util import now_iso as _now_iso
from ._sqlcipher_util import where as _where


class SqlArchRefMixin:
    """Arch-ref reads and writes for a store exposing `_require_unlocked()`.

    The borrowed surface is declared rather than assumed, as `SqlFmeaAssessmentMixin` declares its
    `_conn()`: a mixin that reads attributes its host merely happens to have is a contract no type
    checker can hold, and the host is free to rename what nothing names.
    """

    def _require_unlocked(self) -> Any:
        raise NotImplementedError("provided by the host store")

    def register_arch_ref(
        self,
        assurance_node_id: str,
        arch_artifact_id: str,
        ref_type: str,
    ) -> None:
        conn = self._require_unlocked()
        conn.execute(
            "INSERT OR REPLACE INTO arch_refs (assurance_node_id, arch_artifact_id, ref_type) "
            "VALUES (?, ?, ?)",
            (assurance_node_id, arch_artifact_id, ref_type),
        )
        conn.commit()

    def mark_arch_ref_resolved(
        self,
        assurance_node_id: str,
        arch_artifact_id: str,
        ref_type: str,
    ) -> None:
        """Set resolved_at timestamp on an existing arch_ref row."""
        conn = self._require_unlocked()
        conn.execute(
            "UPDATE arch_refs SET resolved_at = ? "
            "WHERE assurance_node_id = ? AND arch_artifact_id = ? AND ref_type = ?",
            (_now_iso(), assurance_node_id, arch_artifact_id, ref_type),
        )
        conn.commit()

    def retarget_arch_refs(self, *, new_arch_artifact_id: str) -> int:
        """Point every ref that names this artifact under an older slug at its current id.

        A row-by-row update rather than one statement, because "the same artifact under a different
        spelling" is a property of the id (its `PREFIX@epoch.random` stem), not something SQL can
        express — and the rule lives in the domain, where the repository's own referrer rewrites take
        it from.
        """
        conn = self._require_unlocked()
        moved = 0
        for ref in refs_to_retarget(self.list_arch_refs(), new_arch_artifact_id=new_arch_artifact_id):
            conn.execute(
                "UPDATE arch_refs SET arch_artifact_id = ? "
                "WHERE assurance_node_id = ? AND arch_artifact_id = ? AND ref_type = ?",
                (
                    new_arch_artifact_id,
                    str(ref["assurance_node_id"]),
                    str(ref["arch_artifact_id"]),
                    str(ref["ref_type"]),
                ),
            )
            moved += 1
        if moved:
            conn.commit()
        return moved

    def list_arch_refs(
        self,
        *,
        assurance_node_id: str | None = None,
        arch_artifact_id: str | None = None,
    ) -> list[dict[str, object]]:
        conn = self._require_unlocked()
        where, params = _where(
            {"assurance_node_id": assurance_node_id, "arch_artifact_id": arch_artifact_id}
        )
        rows = conn.execute(f"SELECT * FROM arch_refs {where}", params).fetchall()
        return as_arch_ref_records(list(rows))

