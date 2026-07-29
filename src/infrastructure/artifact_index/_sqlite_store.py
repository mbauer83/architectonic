from __future__ import annotations

import json
import os
import queue
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Callable, Generator

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)

from ._diagram_fts import diagram_fts_row
from ._mem_store import _MemStore
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
    "src_multiplicity,tgt_multiplicity,specialization,group_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_DIAGRAM = (
    "INSERT INTO diagrams (artifact_id,artifact_type,name,diagram_type,version,"
    "status,path,scope,extra_json,group_name) VALUES (?,?,?,?,?,?,?,?,?,?)"
)
_INS_DOCUMENT = (
    "INSERT INTO documents (artifact_id,doc_type,title,status,path,scope,"
    "keywords_json,sections_json,content_text,extra_json,group_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_EDGE = (
    "INSERT INTO entity_context_edges "
    "(entity_id,connection_id,direction_bucket,other_entity_id,conn_type,"
    "connection_status,connection_version,source_id,target_id,source_name,"
    "target_name,source_artifact_type,target_artifact_type,source_domain,"
    "target_domain,source_scope,target_scope,path,content_text,"
    "associated_entities_json,src_multiplicity,tgt_multiplicity,specialization) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INS_EFTS = (
    "INSERT INTO entities_fts "
    "(artifact_id,name,artifact_type,domain,subdomain,keywords,content_text,display_label)"
    " VALUES (?,?,?,?,?,?,?,?)"
)
_INS_CFTS = "INSERT INTO connections_fts (artifact_id,source,target,conn_type,content_text) VALUES (?,?,?,?,?)"
_INS_DFTS = "INSERT INTO diagrams_fts (artifact_id,name,diagram_type,artifact_type,member_names) VALUES (?,?,?,?,?)"
_INS_DOCFTS = "INSERT INTO documents_fts (artifact_id,title,doc_type,keywords,content_text) VALUES (?,?,?,?,?)"
_INS_ATTR_TYPE_REF = (
    "INSERT INTO attribute_type_refs (diagram_id,classifier_local_id,attr_name,type_id) VALUES (?,?,?,?)"
)


_READ_POOL_SIZE = min(max(os.cpu_count() or 4, 4), 8)


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
        # Read connection pool: each caller gets its own connection so SQLite
        # SHARED locks can coexist and reads truly parallelise up to pool size.
        # Pool connections share the same in-memory cache as self._conn and
        # always see its committed writes automatically.
        self._read_pool: queue.Queue[sqlite3.Connection] = queue.Queue()
        for _ in range(_READ_POOL_SIZE):
            c = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
            c.row_factory = sqlite3.Row
            self._read_pool.put(c)

    @contextmanager
    def reader(self) -> Generator[sqlite3.Connection, None, None]:
        """Check out a read connection from the pool and yield it.

        Must be called inside _lock.reading() so the write connection cannot
        be modifying tables while a pool connection is reading them.
        """
        conn = self._read_pool.get()
        try:
            yield conn
        finally:
            self._read_pool.put(conn)

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
            self._conn.execute(_INS_ENTITY, self._entity_row(rec))
            if self._fts_enabled:
                self._conn.execute("DELETE FROM entities_fts WHERE artifact_id=?", (rec.artifact_id,))
                self._conn.execute(
                    _INS_EFTS,
                    (
                        rec.artifact_id,
                        rec.name,
                        rec.artifact_type,
                        rec.domain,
                        rec.subdomain,
                        " ".join(rec.keywords),
                        rec.content_text,
                        rec.display_label,
                    ),
                )

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
            self._conn.execute(_INS_CONNECTION, self._connection_row(rec))
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
            self._conn.execute(_INS_DIAGRAM, self._diagram_row(rec))
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
            self._conn.execute(_INS_DOCUMENT, self._document_row(rec))
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
                "entity_context_edges",
                "entity_context_stats",
                "attribute_type_refs",
            ):
                self._conn.execute(f"DELETE FROM {t}")  # noqa: S608
            if self._fts_enabled:
                for t in ("entities_fts", "connections_fts", "diagrams_fts", "documents_fts"):
                    self._conn.execute(f"DELETE FROM {t}")  # noqa: S608
            self._conn.executemany(_INS_ENTITY, [self._entity_row(r) for r in self._mem.entities.values()])
            self._conn.executemany(_INS_CONNECTION, [self._connection_row(r) for r in self._mem.connections.values()])
            self._conn.executemany(_INS_DIAGRAM, [self._diagram_row(r) for r in self._mem.diagrams.values()])
            self._conn.executemany(_INS_DOCUMENT, [self._document_row(r) for r in self._mem.documents.values()])
            attr_ref_rows = [
                (diagram_id, clf_id, attr_name, type_id)
                for diagram_id, refs in self._mem.attribute_type_refs.items()
                for clf_id, attr_name, type_id in refs
            ]
            if attr_ref_rows:
                self._conn.executemany(_INS_ATTR_TYPE_REF, attr_ref_rows)
            if self._fts_enabled:
                self._conn.executemany(
                    _INS_EFTS,
                    [
                        (
                            r.artifact_id,
                            r.name,
                            r.artifact_type,
                            r.domain,
                            r.subdomain,
                            " ".join(r.keywords),
                            r.content_text,
                            r.display_label,
                        )
                        for r in self._mem.entities.values()
                    ],
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

    # ── Row builders ─────────────────────────────────────────────────────────

    def _entity_row(self, r: EntityRecord) -> tuple[object, ...]:
        return (
            r.artifact_id,
            r.artifact_type,
            r.name,
            r.version,
            r.status,
            r.domain,
            r.subdomain,
            str(r.path),
            self._scope(r.path),
            json.dumps(list(r.keywords)),
            json.dumps(r.extra, sort_keys=True),
            r.content_text,
            json.dumps(r.display_blocks, sort_keys=True),
            r.display_label,
            r.display_alias,
            r.host_diagram_id,
            r.group,
        )

    def _connection_row(self, r: ConnectionRecord) -> tuple[str, ...]:
        return (
            r.artifact_id,
            r.source,
            r.target,
            r.conn_type,
            r.version,
            r.status,
            str(r.path),
            self._scope(r.path),
            json.dumps(r.extra, sort_keys=True),
            r.content_text,
            json.dumps(list(r.associated_entities)),
            r.src_multiplicity,
            r.tgt_multiplicity,
            r.specialization,
            r.group,
        )

    def _diagram_row(self, r: DiagramRecord) -> tuple[str, ...]:
        return (
            r.artifact_id,
            r.artifact_type,
            r.name,
            r.diagram_type,
            r.version,
            r.status,
            str(r.path),
            self._scope(r.path),
            json.dumps(r.extra, sort_keys=True),
            r.group,
        )

    def _document_row(self, r: DocumentRecord) -> tuple[str, ...]:
        return (
            r.artifact_id,
            r.doc_type,
            r.title,
            r.status,
            str(r.path),
            self._scope(r.path),
            json.dumps(list(r.keywords)),
            json.dumps(list(r.sections)),
            r.content_text,
            json.dumps(r.extra, sort_keys=True),
            r.group,
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
            rec.specialization,
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
