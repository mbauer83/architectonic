from __future__ import annotations

import json
import sqlite3
from contextlib import AbstractContextManager
from functools import lru_cache
from pathlib import Path
from typing import Callable

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
)

from ._diagram_fts import diagram_fts_row
from ._mem_store import _MemStore
from ._read_pool import ReadConnectionPool
from ._sqlite_rows import (
    connection_row,
    diagram_row,
    document_row,
    entity_fts_row,
    entity_row,
    note_fts_row,
    note_row,
)
from ._sqlite_schema import FTS_SQL, SCHEMA_SQL

_INS_ENTITY = (
    "INSERT INTO entities (artifact_id,artifact_type,name,version,status,domain,"
    "subdomain,path,scope,keywords_json,extra_json,content_text,"
    "display_blocks_json,display_label,display_alias,host_diagram_id,group_name)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_CONNECTION = (
    "INSERT INTO connections (artifact_id,source,target,conn_type,version,status,"
    "path,scope,extra_json,content_text,associated_entities_json,"
    "src_multiplicity,tgt_multiplicity,specializations_json,group_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_DIAGRAM = (
    "INSERT INTO diagrams (artifact_id,artifact_type,name,diagram_type,version,"
    "status,path,scope,extra_json,group_name) VALUES (?,?,?,?,?,?,?,?,?,?)"
)
_INS_DOCUMENT = (
    "INSERT INTO documents (artifact_id,doc_type,title,status,path,scope,"
    "keywords_json,sections_json,content_text,extra_json,group_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_NOTE = (
    "INSERT INTO scratchpad_notes (artifact_id,scratchpad_id,scratchpad_name,note_id,title,body,"
    "element_type,domain,area,status,path,scope,group_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_EDGE = (
    "INSERT INTO entity_context_edges "
    "(entity_id,connection_id,direction_bucket,other_entity_id,conn_type,"
    "connection_status,connection_version,source_id,target_id,source_name,"
    "target_name,source_artifact_type,target_artifact_type,source_domain,"
    "target_domain,source_scope,target_scope,path,content_text,"
    "associated_entities_json,src_multiplicity,tgt_multiplicity,specializations_json) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_EFTS = (
    "INSERT INTO entities_fts "
    "(artifact_id,name,artifact_type,domain,subdomain,keywords,content_text,display_label,host_diagram_id)"
    " VALUES (?,?,?,?,?,?,?,?,?)"
)
_INS_CFTS = "INSERT INTO connections_fts (artifact_id,source,target,conn_type,content_text) VALUES (?,?,?,?,?)"
_INS_DFTS = "INSERT INTO diagrams_fts (artifact_id,name,diagram_type,artifact_type,member_names) VALUES (?,?,?,?,?)"
_INS_DOCFTS = "INSERT INTO documents_fts (artifact_id,title,doc_type,keywords,content_text) VALUES (?,?,?,?,?)"
_INS_NOTEFTS = (
    "INSERT INTO scratchpad_notes_fts "
    "(artifact_id,scratchpad_id,title,body,element_type,domain,scratchpad_name)"
    " VALUES (?,?,?,?,?,?,?)"
)
_INS_ATTR_TYPE_REF = (
    "INSERT INTO attribute_type_refs (diagram_id,classifier_local_id,attr_name,type_id) VALUES (?,?,?,?)"
)




@lru_cache(maxsize=None)
def _is_symmetric_conn(conn_type: str) -> bool:
    from src.domain.modules.module_types import ConnectionTypeName  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    info = get_module_registry().find_connection_type(ConnectionTypeName(conn_type))
    return info.symmetric if info is not None else False


class _SqliteStore:
    def __init__(self, name_hash: str, mem: _MemStore, scope_fn: Callable[[Path], str]) -> None:
        self._uri = f"file:arch-artifact-index-{name_hash}?mode=memory&cache=shared"
        self._conn = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mem = mem
        self._scope = scope_fn
        self._fts_enabled = True
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)
        try:
            with self._conn:
                self._conn.executescript(FTS_SQL)
        except sqlite3.OperationalError:
            self._fts_enabled = False
        self._read_pool = ReadConnectionPool(self._uri)

    def reader(self) -> AbstractContextManager[sqlite3.Connection]:
        """Check out a pooled read connection. See `ReadConnectionPool.reader` for the why."""
        return self._read_pool.reader()

    def close(self) -> None:
        """Release the write connection and every pooled reader. Idempotent.

        Without this, connections were reclaimed only when the collector got to them —
        `ResourceWarning: unclosed database`, 433 once warnings became errors, and one shared-cache
        database held alive per index for a served process's whole life.
        """
        self._read_pool.close()
        self._conn.close()

    @property
    def fts_enabled(self) -> bool:
        return self._fts_enabled

    # ── Write operations ──────────────────────────────────────────────────────

    def upsert_entity(self, rec: EntityRecord) -> None:
        old = self._mem.entities.get(rec.artifact_id)
        if old is not None:
            self._mem.unindex_entity(old)
        self._mem.entities[rec.artifact_id] = rec
        self._mem.index_entity(rec)
        with self._conn:
            self._conn.execute("DELETE FROM entities WHERE artifact_id=?", (rec.artifact_id,))
            self._conn.execute(_INS_ENTITY, entity_row(rec, self._scope))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM entities_fts WHERE artifact_id=?", (rec.artifact_id,))
                self._conn.execute(_INS_EFTS, entity_fts_row(rec))

    def delete_entity(self, artifact_id: str) -> None:
        old = self._mem.entities.pop(artifact_id, None)
        if old is not None:
            self._mem.unindex_entity(old)
        with self._conn:
            self._conn.execute("DELETE FROM entities WHERE artifact_id=?", (artifact_id,))
            self._conn.execute("DELETE FROM entity_context_edges WHERE entity_id=?", (artifact_id,))
            self._conn.execute("DELETE FROM entity_context_stats WHERE entity_id=?", (artifact_id,))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM entities_fts WHERE artifact_id=?", (artifact_id,))

    def upsert_connection(self, rec: ConnectionRecord) -> None:
        # The one door into the read model for an individual connection, whichever producer
        # it came from — a parsed .outgoing.md or a diagram's own connection block. The
        # in-memory half owns its own dicts and invariants, and hands back the record it
        # actually stored, so the SQLite rows below carry the same canonical endpoints.
        rec = self._mem.put_connection(rec)
        with self._conn:
            self._conn.execute("DELETE FROM connections WHERE artifact_id=?", (rec.artifact_id,))
            self._conn.execute(_INS_CONNECTION, connection_row(rec, self._scope))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM connections_fts WHERE artifact_id=?", (rec.artifact_id,))
                self._conn.execute(
                    _INS_CFTS,
                    (rec.artifact_id, rec.source, rec.target, rec.conn_type, rec.content_text),
                )

    def delete_connection(self, artifact_id: str) -> None:
        old = self._mem.connections.pop(artifact_id, None)
        if old is not None:
            self._mem.unindex_connection(old)
        with self._conn:
            self._conn.execute("DELETE FROM connections WHERE artifact_id=?", (artifact_id,))
            self._conn.execute("DELETE FROM entity_context_edges WHERE connection_id=?", (artifact_id,))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM connections_fts WHERE artifact_id=?", (artifact_id,))

    def upsert_diagram(self, rec: DiagramRecord) -> None:
        old = self._mem.diagrams.get(rec.artifact_id)
        if old is not None:
            self._mem.unindex_diagram(old)
        self._mem.diagrams[rec.artifact_id] = rec
        self._mem.index_diagram(rec)
        with self._conn:
            self._conn.execute("DELETE FROM diagrams WHERE artifact_id=?", (rec.artifact_id,))
            self._conn.execute(_INS_DIAGRAM, diagram_row(rec, self._scope))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM diagrams_fts WHERE artifact_id=?", (rec.artifact_id,))
                self._conn.execute(_INS_DFTS, diagram_fts_row(rec, self._mem))

    def delete_diagram(self, artifact_id: str) -> None:
        old = self._mem.diagrams.pop(artifact_id, None)
        if old is not None:
            self._mem.unindex_diagram(old)
        with self._conn:
            self._conn.execute("DELETE FROM diagrams WHERE artifact_id=?", (artifact_id,))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM diagrams_fts WHERE artifact_id=?", (artifact_id,))

    def upsert_document(self, rec: DocumentRecord) -> None:
        self._mem.documents[rec.artifact_id] = rec
        self._mem.document_by_path[rec.path.resolve()] = rec.artifact_id
        with self._conn:
            self._conn.execute("DELETE FROM documents WHERE artifact_id=?", (rec.artifact_id,))
            self._conn.execute(_INS_DOCUMENT, document_row(rec, self._scope))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM documents_fts WHERE artifact_id=?", (rec.artifact_id,))
                self._conn.execute(
                    _INS_DOCFTS,
                    (
                        rec.artifact_id,
                        rec.title,
                        rec.doc_type,
                        " ".join(rec.keywords),
                        rec.content_text,
                    ),
                )

    def delete_document(self, artifact_id: str) -> None:
        old = self._mem.documents.pop(artifact_id, None)
        if old is not None:
            self._mem.document_by_path.pop(old.path.resolve(), None)
        with self._conn:
            self._conn.execute("DELETE FROM documents WHERE artifact_id=?", (artifact_id,))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM documents_fts WHERE artifact_id=?", (artifact_id,))

    def replace_scratchpad_notes(self, scratchpad_id: str, notes: list[ScratchpadNoteRecord]) -> None:
        """Re-index one scratchpad's notes, whole.

        Note-grained upsert would be the wrong seam: a scratchpad is loaded, saved and versioned
        whole, and a note that vanished from the file has no event of its own to be deleted by. So
        the unit of change here is the file, exactly as it is everywhere else in this feature.
        """
        self.delete_scratchpad_notes(scratchpad_id)
        self._mem.scratchpad_notes.update({rec.artifact_id: rec for rec in notes})
        if notes:
            self._mem.notes_by_scratchpad[scratchpad_id] = {rec.artifact_id for rec in notes}
        with self._conn:
            self._conn.executemany(_INS_NOTE, [note_row(rec, self._scope) for rec in notes])
            if self._fts_enabled:
                self._conn.executemany(_INS_NOTEFTS, [note_fts_row(rec) for rec in notes])

    def delete_scratchpad_notes(self, scratchpad_id: str) -> None:
        addresses = self._mem.notes_by_scratchpad.pop(scratchpad_id, set())
        for address in addresses:
            self._mem.scratchpad_notes.pop(address, None)
        with self._conn:
            if self._fts_enabled:
                self._conn.execute(
                    "DELETE FROM scratchpad_notes_fts WHERE scratchpad_id=?", (scratchpad_id,)
                )
            self._conn.execute("DELETE FROM scratchpad_notes WHERE scratchpad_id=?", (scratchpad_id,))

    def upsert_attribute_type_refs(self, diagram_id: str, refs: list[tuple[str, str, str]]) -> None:
        self._mem.attribute_type_refs[diagram_id] = refs
        with self._conn:
            self._conn.execute("DELETE FROM attribute_type_refs WHERE diagram_id=?", (diagram_id,))
            if refs:
                self._conn.executemany(_INS_ATTR_TYPE_REF, [(diagram_id, *r) for r in refs])

    def delete_attribute_type_refs(self, diagram_id: str) -> None:
        self._mem.attribute_type_refs.pop(diagram_id, None)
        with self._conn:
            self._conn.execute("DELETE FROM attribute_type_refs WHERE diagram_id=?", (diagram_id,))

    # ── Full rebuild ──────────────────────────────────────────────────────────

    def rebuild(self) -> None:
        with self._conn:
            for t in (
                "entities",
                "connections",
                "diagrams",
                "documents",
                "scratchpad_notes",
                "entity_context_edges",
                "entity_context_stats",
                "attribute_type_refs",
            ):
                self._conn.execute(f"DELETE FROM {t}")  # noqa: S608
            if self._fts_enabled:
                for t in (
                    "entities_fts", "connections_fts", "diagrams_fts", "documents_fts",
                    "scratchpad_notes_fts",
                ):
                    self._conn.execute(f"DELETE FROM {t}")  # noqa: S608
            self._conn.executemany(_INS_ENTITY, [entity_row(r, self._scope) for r in self._mem.entities.values()])
            self._conn.executemany(
                _INS_CONNECTION, [connection_row(r, self._scope) for r in self._mem.connections.values()]
            )
            self._conn.executemany(_INS_DIAGRAM, [diagram_row(r, self._scope) for r in self._mem.diagrams.values()])
            self._conn.executemany(_INS_DOCUMENT, [document_row(r, self._scope) for r in self._mem.documents.values()])
            self._conn.executemany(
                _INS_NOTE, [note_row(r, self._scope) for r in self._mem.scratchpad_notes.values()]
            )
            attr_ref_rows = [
                (diagram_id, clf_id, attr_name, type_id)
                for diagram_id, refs in self._mem.attribute_type_refs.items()
                for clf_id, attr_name, type_id in refs
            ]
            if attr_ref_rows:
                self._conn.executemany(_INS_ATTR_TYPE_REF, attr_ref_rows)
            if self._fts_enabled:
                self._conn.executemany(
                    _INS_EFTS, [entity_fts_row(r) for r in self._mem.entities.values()]
                )
                self._conn.executemany(
                    _INS_CFTS,
                    [
                        (r.artifact_id, r.source, r.target, r.conn_type, r.content_text)
                        for r in self._mem.connections.values()
                    ],
                )
                self._conn.executemany(_INS_DFTS, [diagram_fts_row(r, self._mem) for r in self._mem.diagrams.values()])
                self._conn.executemany(
                    _INS_DOCFTS,
                    [
                        (r.artifact_id, r.title, r.doc_type, " ".join(r.keywords), r.content_text)
                        for r in self._mem.documents.values()
                    ],
                )
                self._conn.executemany(
                    _INS_NOTEFTS, [note_fts_row(r) for r in self._mem.scratchpad_notes.values()]
                )
        self.rebuild_context_projection()

    # ── Projection maintenance ────────────────────────────────────────────────

    def rebuild_context_projection(self) -> None:
        rows = [row for rec in self._mem.connections.values() for row in self._context_rows(rec)]
        with self._conn:
            if rows:
                self._conn.executemany(_INS_EDGE, rows)
            self._conn.execute(
                "INSERT INTO entity_context_stats (entity_id,conn_in,conn_out,conn_sym) "
                "SELECT entity_id, SUM(direction_bucket='inbound'),"
                " SUM(direction_bucket='outbound'), SUM(direction_bucket='symmetric') "
                "FROM entity_context_edges GROUP BY entity_id"
            )

    def rebuild_context_for(self, entity_id: str) -> None:
        # Use the entity→connections secondary index for O(K) lookup instead of O(N).
        relevant_ids = self._mem.connections_by_entity.get(entity_id, set())
        rows = [
            row
            for cid in relevant_ids
            if (rec := self._mem.connections.get(cid)) is not None
            for row in self._context_rows(rec)
            if row[0] == entity_id
        ]
        with self._conn:
            self._conn.execute("DELETE FROM entity_context_edges WHERE entity_id=?", (entity_id,))
            if rows:
                self._conn.executemany(_INS_EDGE, rows)
            self._conn.execute("DELETE FROM entity_context_stats WHERE entity_id=?", (entity_id,))
            self._conn.execute(
                "INSERT INTO entity_context_stats (entity_id,conn_in,conn_out,conn_sym) "
                "SELECT entity_id, SUM(direction_bucket='inbound'),"
                " SUM(direction_bucket='outbound'), SUM(direction_bucket='symmetric') "
                "FROM entity_context_edges WHERE entity_id=? GROUP BY entity_id",
                (entity_id,),
            )

    def _context_rows(self, rec: ConnectionRecord) -> list[tuple[str, ...]]:
        src = self._mem.entities.get(rec.source)
        tgt = self._mem.entities.get(rec.target)
        shared: tuple[str, ...] = (
            rec.conn_type,
            rec.status,
            rec.version,
            rec.source,
            rec.target,
            src.name if src and src.name else rec.source,
            tgt.name if tgt and tgt.name else rec.target,
            src.artifact_type if src else "unknown",
            tgt.artifact_type if tgt else "unknown",
            src.domain if src else "unknown",
            tgt.domain if tgt else "unknown",
            self._scope(src.path) if src else "unknown",
            self._scope(tgt.path) if tgt else "unknown",
            str(rec.path),
            rec.content_text,
            json.dumps(list(rec.associated_entities)),
            rec.src_multiplicity,
            rec.tgt_multiplicity,
            json.dumps(list(rec.specializations)),
        )
        if _is_symmetric_conn(rec.conn_type):
            rows: list[tuple[str, ...]] = [(rec.source, rec.artifact_id, "symmetric", rec.target, *shared)]
            if rec.target != rec.source:
                rows.append((rec.target, rec.artifact_id, "symmetric", rec.source, *shared))
            return rows
        return [
            (rec.source, rec.artifact_id, "outbound", rec.target, *shared),
            (rec.target, rec.artifact_id, "inbound", rec.source, *shared),
        ]
