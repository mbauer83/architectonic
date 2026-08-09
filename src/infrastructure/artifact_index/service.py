from __future__ import annotations

import hashlib
import threading
from collections import Counter
from pathlib import Path
from typing import Callable, Literal, TypeVar

from src.application.artifacts._query_helpers import (
    matches_connection,
    matches_connection_sets,
    matches_diagram,
    matches_diagram_sets,
    matches_entity,
    matches_entity_sets,
    read_connection,
    read_diagram,
    read_document,
    read_entity,
    to_set,
)
from src.application.ports import Candidate
from src.config.workspace_paths import infer_repo_scope
from src.domain.ontology_representation.artifact_types import (
    ALL_SEARCHABLE_KINDS,
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    ScratchpadNoteRecord,
    summary_from_connection,
    summary_from_diagram,
    summary_from_document,
    summary_from_entity,
)
from src.infrastructure.app_bootstrap import process_runtime_catalogs

from . import _sqlite_queries as _q
from ._identity_resolver import _IdentityResolver
from ._mem_store import _MemStore
from ._reverse_reference_queries import _EntityIds, _ReverseReferenceQueries
from ._rwlock import _RWLock
from ._scope_registry import _ScopeRegistry
from ._scratchpad_note_queries import _ScratchpadNoteQueries
from ._service_incremental import (
    _apply_entity_record,
    _apply_outgoing_records,
    apply_diagram_change,
    apply_document_change,
    apply_scratchpad_change,
    classify_path_change,
)
from ._service_scan import scan_mount
from ._sqlite_store import _SqliteStore
from .bootstrap import normalize_mounts, service_key
from .types import EntityContextConnection, EntityContextReadModel
from .versioning import ReadModelVersion, build_read_model_etag

_T = TypeVar("_T", EntityRecord, ConnectionRecord, DiagramRecord, DocumentRecord, ScratchpadNoteRecord)

_CHANGE_APPLIERS = {
    "outgoing": lambda service, path, data: _apply_outgoing_records(path, data, service._mem, service._db),
    "entity": lambda service, path, data: _apply_entity_record(path, data, service._mem, service._db),
    "diagram": lambda service, path, data: apply_diagram_change(
        path, service._mem, service._db, parsed=data,
        workspace_types=service._get_workspace_types(),
        attr_type_ref_fn=service._attr_type_ref_extractor,
    ),
    "document": lambda service, path, data: apply_document_change(path, service._mem, service._db, parsed=data),
    "scratchpad": lambda service, path, data: apply_scratchpad_change(
        path, service._mem, service._db, parsed=data
    ),
}


class ArtifactIndex(_ReverseReferenceQueries, _ScratchpadNoteQueries):
    def __init__(self, repo_root: Path | list[Path] | list[RepoMount]) -> None:
        mounts = normalize_mounts(repo_root)
        self.repo_mounts: list[RepoMount] = mounts
        self.repo_roots: list[Path] = [m.root for m in mounts]
        self.repo_root: Path = mounts[0].root
        self._scope_key = service_key(mounts)
        self._lock = _RWLock()
        self._init_lock = threading.Lock()  # guards one-time initialization only
        self._ready = threading.Event()
        self._generation = 0
        self._etag = build_read_model_etag(self._scope_key, 0)
        self._mem = _MemStore()
        name_hash = hashlib.blake2b(service_key(mounts).encode("utf-8"), digest_size=10).hexdigest()
        self._db = _SqliteStore(name_hash, self._mem, self.scope_for_path)
        self._registry = _ScopeRegistry(self._mem, self._lock, self._ensure_loaded, self.scope_for_path)
        self._identity = _IdentityResolver(self._mem, self._lock, self._ensure_loaded, self.scope_for_path)

    def close(self) -> None:
        """Release the index's database connections. Idempotent.

        The delegation this class was missing: `_SqliteStore` owns the connections and callers hold an
        `ArtifactIndex`, so without a method here the only way to release them was to reach through to
        the private store — which is the workaround this codebase rejects on principle.
        """
        self._db.close()

    def __enter__(self) -> ArtifactIndex:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _ensure_loaded(self) -> None:
        if self._ready.is_set():
            return
        with self._init_lock:
            if not self._ready.is_set():
                self.refresh()

    def _get_domain_names(self) -> frozenset[str]:

        return process_runtime_catalogs().ontology.known_domain_names()

    def _get_workspace_types(self) -> dict[str, frozenset[str]]:
        from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

        def _ws(dk: DiagramTypeModule) -> frozenset[str]:
            return frozenset(
                oe.entity_type for oe in dk.ui_config.diagram_only_types if oe.identity_scope == "workspace"
            )

        return {str(n): ws for n, dk in get_module_registry().all_diagram_types().items() if (ws := _ws(dk))}

    def _attr_type_ref_extractor(self, diag: DiagramRecord) -> list[tuple[str, str, str]]:
        if diag.diagram_type != "datatype":
            return []
        refs: list[tuple[str, str, str]] = []
        raw_de = diag.extra.get("diagram-entities")
        de: dict = raw_de if isinstance(raw_de, dict) else {}
        for clf in (de.get("classifier") or []):
            if not isinstance(clf, dict):
                continue
            clf_id = str(clf.get("id") or "")
            for attr in (clf.get("attributes") or []):
                if not isinstance(attr, dict):
                    continue
                type_ref = attr.get("type")
                if not isinstance(type_ref, dict) or type_ref.get("kind") != "classifier":
                    continue
                type_id = str(type_ref.get("id") or "")
                attr_name = str(attr.get("name") or "")
                if type_id and attr_name:
                    refs.append((clf_id, attr_name, type_id))
        return refs

    def refresh(self) -> None:
        temp = _MemStore()
        domain_names = self._get_domain_names()
        workspace_types = self._get_workspace_types()
        for mount in self.repo_mounts:
            scan_mount(
                mount, temp,
                domain_names=domain_names,
                workspace_types=workspace_types,
                attr_type_ref_fn=self._attr_type_ref_extractor,
            )
        with self._lock.writing():
            self._mem.replace_from(temp)
            # Derived indexes (entities_by_diagram) must precede the SQLite dump: the
            # diagram FTS rows resolve each diagram's member entity names through them.
            self._mem.rebuild_path_indexes()
            self._db.rebuild()
            self._bump_generation()
            self._ready.set()

    def apply_file_changes(self, paths: list[Path]) -> ReadModelVersion:
        self._ensure_loaded()
        normalized = sorted({p.resolve() for p in paths})
        if not normalized:
            return self.read_model_version()
        if any(p.is_dir() for p in normalized):
            self.refresh()
            return self.read_model_version()
        parsed: list[tuple] = []
        domain_names = self._get_domain_names()
        for path in normalized:
            change = classify_path_change(path, self.repo_mounts, domain_names=domain_names)
            if change is None:
                self.refresh()
                return self.read_model_version()
            parsed.append(change)
        with self._lock.writing():
            for kind, path, data in parsed:
                _CHANGE_APPLIERS[kind](self, path, data)
            self._bump_generation()
        return self.read_model_version()

    def read_model_version(self) -> ReadModelVersion:
        self._ensure_loaded()
        return ReadModelVersion(generation=self._generation, etag=self._etag)

    def generation(self) -> int:
        self._ensure_loaded()
        return self._generation

    # ── Point lookups ─────────────────────────────────────────────────────────

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.entity(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.connection(artifact_id)

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.diagram(artifact_id)

    def get_document(self, artifact_id: str) -> DocumentRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.document(artifact_id)

    # ── Filtered list queries ─────────────────────────────────────────────────

    def _list_sorted(self, collection: dict[str, _T], predicate: Callable[[_T], bool]) -> list[_T]:
        self._ensure_loaded()
        with self._lock.reading():
            results = [v for v in collection.values() if predicate(v)]
        return sorted(results, key=lambda r: r.artifact_id)

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[EntityRecord]:
        return self._list_sorted(
            self._mem.entities,
            lambda r: matches_entity(
                r,
                artifact_type=artifact_type,
                domain=domain,
                subdomain=subdomain,
                status=status,
                group=group,
            ),
        )

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ConnectionRecord]:
        return self._list_sorted(
            self._mem.connections,
            lambda r: matches_connection(
                r,
                conn_type=conn_type,
                source=source,
                target=target,
                status=status,
                group=group,
            ),
        )

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DiagramRecord]:
        return self._list_sorted(
            self._mem.diagrams,
            lambda r: matches_diagram(
                r,
                diagram_type=diagram_type,
                status=status,
                group=group,
            ),
        )

    def list_documents(
        self,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DocumentRecord]:
        return self._list_sorted(
            self._mem.documents,
            lambda r: (doc_type is None or r.doc_type == doc_type)
            and (status is None or r.status == status)
            and (group is None or r.group == group),
        )

    def list_artifacts(
        self,
        *,
        artifact_type: str | list[str] | None = None,
        domain: str | list[str] | None = None,
        status: str | list[str] | None = None,
        include_entities: bool = True,
        include_connections: bool = False,
        include_diagrams: bool = False,
        include_documents: bool = False,
    ) -> list[ArtifactSummary]:
        self._ensure_loaded()
        types = to_set(artifact_type)
        domains = {d.lower() for d in to_set(domain)}
        statuses = to_set(status)
        with self._lock.reading():
            out: list[ArtifactSummary] = [
                summary_from_entity(r)
                for r in self._mem.entities.values()
                if include_entities and matches_entity_sets(r, types, domains, statuses)
            ]
            if include_connections:
                out.extend(
                    summary_from_connection(r)
                    for r in self._mem.connections.values()
                    if matches_connection_sets(r, statuses)
                )
            if include_diagrams:
                out.extend(
                    summary_from_diagram(r)
                    for r in self._mem.diagrams.values()
                    if matches_diagram_sets(r, types, statuses)
                )
            if include_documents:
                out.extend(
                    summary_from_document(r)
                    for r in self._mem.documents.values()
                    if (not statuses or r.status in statuses)
                )
        return sorted(out, key=lambda s: s.artifact_id)

    # ── Richer reads ──────────────────────────────────────────────────────────

    def read_artifact(
        self,
        artifact_id: str,
        *,
        mode: Literal["summary", "full"] = "summary",
        section: str | None = None,
    ) -> dict[str, object] | None:
        self._ensure_loaded()
        with self._lock.reading():
            artifact_id = self._mem.canonical_id(artifact_id)
            return (
                read_entity(ent, mode=mode) if (ent := self._mem.entities.get(artifact_id)) is not None
                else read_connection(conn, mode=mode) if (conn := self._mem.connections.get(artifact_id)) is not None
                else read_diagram(diag, mode=mode) if (diag := self._mem.diagrams.get(artifact_id)) is not None
                else read_document(doc, mode=mode, section=section)
                if (doc := self._mem.documents.get(artifact_id)) is not None
                else None
            )

    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None:
        self._ensure_loaded()
        with self._lock.reading():
            return (
                summary_from_entity(ent) if (ent := self._mem.entity(artifact_id)) is not None
                else summary_from_connection(conn) if (conn := self._mem.connection(artifact_id)) is not None
                else summary_from_diagram(diag) if (diag := self._mem.diagram(artifact_id)) is not None
                else summary_from_document(doc) if (doc := self._mem.document(artifact_id)) is not None
                else None
            )

    def read_entity_context(self, artifact_id: str) -> EntityContextReadModel | None:
        self._ensure_loaded()
        with self._lock.reading():
            entity = self._mem.entity(artifact_id)
            if entity is None:
                return None
            entity_data: dict[str, object] = {
                "artifact_id": entity.artifact_id,
                "artifact_type": entity.artifact_type,
                "name": entity.name,
                "version": entity.version,
                "status": entity.status,
                "domain": entity.domain,
                "subdomain": entity.subdomain,
                "record_type": "entity",
                "path": str(entity.path),
                "content_snippet": entity.content_text[:240],
                "keywords": list(entity.keywords),
                "specializations": list(entity.specializations),
                "content_text": entity.content_text,
                "display_blocks": entity.display_blocks,
                "extra": entity.extra,
            }
            with self._db.reader() as conn:
                return _q.entity_context(conn, artifact_id, entity_data, self._generation, self._etag)

    def stats(self) -> dict[str, object]:
        self._ensure_loaded()
        with self._lock.reading():
            ents, conns = list(self._mem.entities.values()), list(self._mem.connections.values())
            diags, docs = list(self._mem.diagrams.values()), list(self._mem.documents.values())
        return {
            "entities": len(ents), "connections": len(conns),
            "diagrams": len(diags), "documents": len(docs),
            "entities_by_domain": dict(Counter(e.domain for e in ents)),
            "connections_by_type": dict(Counter(c.conn_type for c in conns)),
            "documents_by_type": dict(Counter(d.doc_type for d in docs)),
            "entities_by_group": dict(Counter(e.group for e in ents)),
            "diagrams_by_group": dict(Counter(d.group for d in diags)),
            "documents_by_group": dict(Counter(d.group for d in docs)),
        }

    # ── Connection queries ────────────────────────────────────────────────────

    def connection_counts(self) -> dict[str, tuple[int, int, int]]:
        self._ensure_loaded()
        with self._lock.reading(), self._db.reader() as conn:
            return _q.all_connection_stats(conn)

    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]:
        self._ensure_loaded()
        with self._lock.reading(), self._db.reader() as conn:
            return _q.connection_stats_for(conn, entity_id)

    def connection_counts_for_entities(self, entity_ids: _EntityIds) -> dict[str, tuple[int, int, int]]:
        self._ensure_loaded()
        with self._lock.reading(), self._db.reader() as conn:
            return _q.connection_stats_for_set(conn, frozenset(entity_ids))

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                cids = _q.connection_ids_by_types(conn, types)
            return [r for cid in cids if (r := self._mem.connections.get(cid)) is not None]

    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ) -> list[ConnectionRecord]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                cids = _q.connection_ids_by_types_for_entity_set(conn, types, frozenset(entity_ids))
            return [r for cid in cids if (r := self._mem.connections.get(cid)) is not None]

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                cids = _q.connection_ids_for(conn, entity_id, direction=direction, conn_type=conn_type)
            return [r for cid in cids if (r := self._mem.connections.get(cid)) is not None]

    def find_neighbors(self, entity_id: str, *, max_hops: int = 1, conn_type: str | None = None) -> dict[str, set[str]]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                return _q.find_neighbors(conn, entity_id, max_hops=max_hops, conn_type=conn_type)

    def search_fts(
        self,
        query: str,
        *,
        limit: int,
        kinds: frozenset[str] = ALL_SEARCHABLE_KINDS,
        excluded_entity_types: frozenset[str] = frozenset(),
    ) -> list[tuple[str, str, float]]:
        self._ensure_loaded()
        with self._lock.reading(), self._db.reader() as conn:
            return _q.search_fts(
                conn, query, limit=limit,
                kinds=kinds,
                excluded_entity_types=excluded_entity_types,
                fts_enabled=self._db.fts_enabled,
            )

    def find_entity_by_workspace_id(
        self,
        artifact_id: str,
        *,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> EntityRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            rec = self._mem.entity(artifact_id)
        if rec is None or scope == "both":
            return rec
        return rec if self.scope_for_path(rec.path) == scope else None

    def find_entities_by_name(
        self,
        name: str,
        *,
        artifact_type: str | None = None,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> list[EntityRecord]:
        self._ensure_loaded()
        norm = name.lower().strip()
        with self._lock.reading():
            return [
                r for r in self._mem.entities.values()
                if r.name.lower().strip() == norm
                and (artifact_type is None or r.artifact_type == artifact_type)
                and (scope == "both" or self.scope_for_path(r.path) == scope)
            ]

    def diagrams_referencing_type_id(self, type_id: str) -> list[tuple[str, str, str]]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                return _q.diagrams_referencing_type(conn, type_id)

    # ── Scope ─────────────────────────────────────────────────────────────────

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        resolved = path.resolve()

        def _scope_for_root(root: Path) -> Literal["enterprise", "engagement"] | None:
            try:
                resolved.relative_to(root)
            except ValueError:
                return None
            return "enterprise" if infer_repo_scope(root) == "enterprise" else "engagement"

        return next(
            (scope for root in self.repo_roots if (scope := _scope_for_root(root)) is not None),
            "unknown",
        )

    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        rec = self.get_entity(artifact_id)
        return self.scope_for_path(rec.path) if rec is not None else "unknown"

    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        rec = self.get_connection(artifact_id)
        return self.scope_for_path(rec.path) if rec is not None else "unknown"

    # ── Registry-style queries (delegated to _ScopeRegistry) ─────────────────

    def entity_ids(self) -> set[str]:
        return self._registry.entity_ids()

    def connection_ids(self) -> set[str]:
        return self._registry.connection_ids()

    def enterprise_entity_ids(self) -> set[str]:
        return self._registry.enterprise_entity_ids()

    def engagement_entity_ids(self) -> set[str]:
        return self._registry.engagement_entity_ids()

    def enterprise_connection_ids(self) -> set[str]:
        return self._registry.enterprise_connection_ids()

    def engagement_connection_ids(self) -> set[str]:
        return self._registry.engagement_connection_ids()

    def enterprise_document_ids(self) -> set[str]:
        return self._registry.enterprise_document_ids()

    def enterprise_diagram_ids(self) -> set[str]:
        return self._registry.enterprise_diagram_ids()

    def entity_status(self, artifact_id: str) -> str | None:
        return self._registry.entity_status(artifact_id)

    def entity_statuses(self) -> dict[str, str]:
        return self._registry.entity_statuses()

    def connection_status(self, artifact_id: str) -> str | None:
        return self._registry.connection_status(artifact_id)

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return self._registry.find_file_by_id(artifact_id)

    def find_all_by_stable_id(self, short: str) -> list[Candidate]:
        return self._identity.find_all_by_stable_id(short)

    def reconcile_short_id(self, short: str) -> None:
        self._identity.reconcile_short_id(short, self.apply_file_changes, self.repo_roots)

    def scan_duplicate_short_ids(self) -> dict[str, list[Path]]:
        return self._identity.scan_duplicates()

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]:
        self._ensure_loaded()
        with self._lock.reading():
            with self._db.reader() as conn:
                rows = _q.connections_for_entity_set(conn, frozenset(entity_ids))
        return [_q.entity_context_connection(row) for row in rows]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _bump_generation(self) -> None:
        self._generation += 1
        self._etag = build_read_model_etag(self._scope_key, self._generation)
