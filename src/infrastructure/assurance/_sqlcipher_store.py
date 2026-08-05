"""SQLCipher-backed confidential assurance store adapter.

Key management: the encryption key is retrieved from the secure credential store
(_credential_store). The DB file is stored at the path given at construction
time (typically .arch-assurance/store.db, gitignored).

Thread-safety: the store is a process singleton served by the backend from a pool
of OS threads (the FastAPI/anyio threadpool for sync REST handlers and FastMCP
tool execution). SQLite/SQLCipher connection objects are bound to the thread that
created them, so each accessing thread gets its **own** connection, opened lazily
and cached thread-locally. Connections run in **WAL** mode with a busy timeout, so
concurrent readers do not block one another or the writer. Application-level write
*serialisation* (single-writer discipline) is provided separately by the assurance
write queue at the MCP/REST boundary; this adapter only guarantees that any thread
can safely talk to the store. ``lock()`` disposes every open connection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.application.assurance.node_sorting import resolve_node_sort
from src.domain.assurance.assurance_node_types import NODE_UPDATABLE
from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import _sqlcipher_analysis as _analysis
from src.infrastructure.assurance._edge_records import as_edge_records
from src.infrastructure.assurance._fmea_assessment_records import SqlFmeaAssessmentMixin
from src.infrastructure.assurance._id_utils import make_edge_id, make_node_id
from src.infrastructure.assurance._node_records import as_node_record, as_node_records
from src.infrastructure.assurance._schema import ASSURANCE_SCHEMA_MIGRATIONS, ASSURANCE_SCHEMA_SQL, SCHEMA_VERSION
from src.infrastructure.assurance._sqlcipher_connection import ThreadLocalConnectionManager
from src.infrastructure.assurance._sqlcipher_util import now_iso as _now_iso
from src.infrastructure.assurance._sqlcipher_util import suppress_c_stderr as _suppress_c_stderr
from src.infrastructure.assurance._sqlcipher_util import where as _where

from ._sql_arch_refs import SqlArchRefMixin

logger = logging.getLogger(__name__)


class SQLCipherAssuranceStore(SqlFmeaAssessmentMixin, SqlArchRefMixin):
    """Adapter implementing ConfidentialAssuranceStore using SQLCipher.

    Connection lifecycle (per-thread WAL connections, generation-based
    invalidation, disposal on lock) is delegated to ThreadLocalConnectionManager.
    The encryption key is held in process memory only between unlock and lock
    (never written to disk).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conns = ThreadLocalConnectionManager(db_path, bootstrap=self._bootstrap_schema)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def is_unlocked(self) -> bool:
        return self._conns.is_open()

    def availability_revision(self) -> int:
        """AvailabilityState port: changes whenever the store locks, unlocks,
        or reconnects — consumers revalidate snapshot tokens against it."""
        return self._conns.availability_revision()

    def unlock(self) -> None:
        # This store's key, scoped to its own path: on a machine holding more than one store,
        # "the" key is ambiguous, and the ambiguity is what let one store's initialisation
        # overwrite another's.
        key = accounts.read(accounts.DB_KEY, self._db_path)
        if key is None:
            raise RuntimeError(
                "Assurance store key not found in credential store. "
                "Run `arch-assurance init` to initialise the store."
            )
        self._conns.open(key)
        logger.info("Assurance store unlocked at %s", self._db_path)

    def lock(self) -> None:
        # Closing checkpoints the write-ahead log first, so locking is also the durability step:
        # a process that locks before it exits leaves no committed pages for the next open to
        # discard. See `_sqlcipher_connection.checkpoint`.
        self._conns.close()
        logger.info("Assurance store locked")

    @staticmethod
    def _bootstrap_schema(conn: Any) -> None:
        """Apply schema + migrations on the first connection; key mismatch → RuntimeError."""
        # Suppress C-library 'ERROR CORE ...' output on key mismatch; the
        # RuntimeError below carries the actionable message instead.
        try:
            with _suppress_c_stderr():
                conn.executescript(ASSURANCE_SCHEMA_SQL)
        except Exception as exc:
            raise RuntimeError(
                "Failed to unlock the assurance store — the keychain key does not match "
                "this database. This usually means the store was re-initialised after the "
                "key was last saved. Run `arch-assurance init --force` to create a fresh "
                "store (existing data will be lost)."
            ) from exc
        for migration_sql in ASSURANCE_SCHEMA_MIGRATIONS:
            try:
                conn.execute(migration_sql)
            except Exception as _exc:  # noqa: BLE001
                if "duplicate column" not in str(_exc):
                    raise
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        conn.commit()

    def _thread_conn_or_none(self) -> Any:
        """Calling thread's connection, or None if locked (archive/signals factory)."""
        return self._conns.get_or_none()

    def _require_unlocked(self) -> Any:
        return self._conns.require()

    def _conn(self) -> Any:
        """The connection the factor-assessment mixin persists through; raises when locked."""
        return self._conns.require()

    def unlocked_connection(self) -> Any:
        """Public handle to the unlocked DB connection for bulk portability operations."""
        return self._require_unlocked()

    # ── Analysis aggregate ──────────────────────────────────────────────────────

    def create_analysis(
        self,
        name: str,
        method: str,
        architecture_anchor_id: str = "",
        *,
        tlp: str = "TLP:WHITE",
        status: str = "draft",
    ) -> str:
        return _analysis.create(
            self._require_unlocked(), name, method, architecture_anchor_id, tlp=tlp, status=status
        )

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None:
        return _analysis.get(self._require_unlocked(), analysis_id)

    def list_analyses(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        return _analysis.list_analyses(self._require_unlocked(), method=method, status=status)

    def update_analysis(self, analysis_id: str, **attrs: object) -> None:
        _analysis.update(self._require_unlocked(), analysis_id, attrs)

    def delete_analysis(self, analysis_id: str) -> None:
        _analysis.delete(self._require_unlocked(), analysis_id)

    # ── Grouping (filing above analyses) ──────────────────────────────────────

    def create_group(self, name: str, description: str = "") -> str:
        return _analysis.create_group(self._require_unlocked(), name, description)

    def get_group(self, group_id: str) -> dict[str, object] | None:
        return _analysis.get_group(self._require_unlocked(), group_id)

    def list_groups(self) -> list[dict[str, object]]:
        return _analysis.list_groups(self._require_unlocked())

    def delete_group(self, group_id: str) -> None:
        """Remove the group. Its analyses survive, unfiled — deleting a folder must never
        delete the analyses inside it."""
        _analysis.delete_group(self._require_unlocked(), group_id)

    # ── Participation (a node taking part in an analysis that did not author it) ──

    def add_analysis_member(self, analysis_id: str, node_id: str) -> None:
        _analysis.add_member(self._require_unlocked(), analysis_id, node_id)

    def remove_analysis_member(self, analysis_id: str, node_id: str) -> None:
        _analysis.remove_member(self._require_unlocked(), analysis_id, node_id)

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        """Node ids drawn into `analysis_id` from elsewhere — authorship is `analysis_id` on
        the node itself and is not repeated here."""
        return _analysis.list_members(self._require_unlocked(), analysis_id)

    def list_participating_analyses(self, node_id: str) -> list[str]:
        return _analysis.participating_analyses(self._require_unlocked(), node_id)

    def list_all_analysis_members(self) -> list[dict[str, object]]:
        """Every membership row, for the portability bundle. Off the port on purpose: callers
        that reason about participation want one analysis' members or one node's analyses, and
        only an export wants the whole join table."""
        return _analysis.list_all_members(self._require_unlocked())

    # ── Node CRUD ─────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict[str, object] | None:
        conn = self._require_unlocked()
        row = conn.execute(
            "SELECT * FROM assurance_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        return as_node_record(row) if row else None

    def list_nodes(
        self,
        *,
        node_type: str | None = None,
        status: str | None = None,
        concern_class: str | None = None,
        tlp: str | None = None,
        analysis_id: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        conn = self._require_unlocked()
        where, params = _where(
            {
                "node_type": node_type, "status": status, "concern_class": concern_class,
                "tlp": tlp, "analysis_id": analysis_id,
            }
        )
        column, direction = resolve_node_sort(sort, order)
        rows = conn.execute(
            f"SELECT * FROM assurance_nodes {where} "
            f"ORDER BY {column} {'DESC' if direction == 'desc' else 'ASC'}, node_id ASC",
            params,
        ).fetchall()
        return as_node_records(list(rows))

    def create_node(
        self,
        node_type: str,
        name: str,
        *,
        status: str = "draft",
        tlp: str = "TLP:WHITE",
        concern_class: str | None = None,
        disposition: str | None = None,
        uca_type: str | None = None,
        failure_type: str | None = None,
        mode: str | None = None,
        binding_status: str | None = None,
        node_role: str | None = None,
        analysis_id: str | None = None,
        attributes: dict[str, object] | None = None,
        content: str = "",
    ) -> str:
        conn = self._require_unlocked()
        node_id = make_node_id(node_type, name)
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO assurance_nodes
                (node_id, node_type, name, status, tlp, concern_class, disposition,
                 uca_type, failure_type, mode, binding_status, node_role, analysis_id,
                 attributes_json, content_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id, node_type, name, status, tlp, concern_class, disposition,
                uca_type, failure_type, mode, binding_status, node_role, analysis_id,
                json.dumps(attributes or {}), content, now, now,
            ),
        )
        conn.commit()
        return node_id

    def update_node(self, node_id: str, **attrs: object) -> None:
        conn = self._require_unlocked()
        sets: list[str] = ["updated_at = ?"]
        params: list[object] = [_now_iso()]
        for k, v in attrs.items():
            if k in NODE_UPDATABLE:
                sets.append(f"{k} = ?")
                params.append(v)
            elif k == "attributes":
                sets.append("attributes_json = ?")
                params.append(json.dumps(v))
        params.append(node_id)
        conn.execute(
            f"UPDATE assurance_nodes SET {', '.join(sets)} WHERE node_id = ?", params
        )
        conn.commit()

    def delete_node(self, node_id: str) -> None:
        """Delete the node and everything keyed to it.

        Edges cascade through their declared foreign keys. `arch_refs` and the participation rows
        are removed here instead: `arch_refs` never declared a foreign key, and a constraint added
        to either table now would only bind stores created afterwards. Deleting explicitly is what
        holds for a store initialised before the omission was found — the shipped one included,
        whose exported seed named 14 nodes that no longer existed.
        """
        conn = self._require_unlocked()
        conn.execute("DELETE FROM arch_refs WHERE assurance_node_id = ?", (node_id,))
        _analysis.remove_all_members_of_node(conn, node_id)
        conn.execute("DELETE FROM assurance_nodes WHERE node_id = ?", (node_id,))
        conn.commit()

    # ── Edge CRUD ─────────────────────────────────────────────────────────────

    def list_edges(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        conn_type: str | None = None,
    ) -> list[dict[str, object]]:
        conn = self._require_unlocked()
        where, params = _where({"source_id": source_id, "target_id": target_id, "conn_type": conn_type})
        rows = conn.execute(
            f"SELECT * FROM assurance_edges {where} ORDER BY created_at", params
        ).fetchall()
        return as_edge_records(list(rows))

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        conn_type: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> str:
        conn = self._require_unlocked()
        edge_id = make_edge_id(source_id, target_id, conn_type)
        now = _now_iso()
        conn.execute(
            "INSERT INTO assurance_edges (edge_id, source_id, target_id, conn_type, attributes_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, source_id, target_id, conn_type, json.dumps(attributes or {}), now),
        )
        conn.commit()
        return edge_id

    def remove_edge(self, edge_id: str) -> None:
        conn = self._require_unlocked()
        conn.execute("DELETE FROM assurance_edges WHERE edge_id = ?", (edge_id,))
        conn.commit()

    def search_nodes(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        conn = self._require_unlocked()
        pattern = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM assurance_nodes
               WHERE name LIKE ? OR content_text LIKE ?
               ORDER BY
                   CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                   created_at
               LIMIT ?""",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        return as_node_records(list(rows))

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, object]:
        conn = self._require_unlocked()
        node_row: dict[str, object] = conn.execute("SELECT COUNT(*) as cnt FROM assurance_nodes").fetchone()
        edge_row: dict[str, object] = conn.execute("SELECT COUNT(*) as cnt FROM assurance_edges").fetchone()
        type_rows = conn.execute(
            "SELECT node_type, COUNT(*) as cnt FROM assurance_nodes GROUP BY node_type"
        ).fetchall()
        return {
            "node_count": node_row["cnt"],
            "edge_count": edge_row["cnt"],
            "by_type": {r["node_type"]: r["cnt"] for r in type_rows},
        }
