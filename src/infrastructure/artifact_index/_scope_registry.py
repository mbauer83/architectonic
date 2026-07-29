"""Scope-aware registry queries over _MemStore — injected into ArtifactIndex."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

from src.domain.artifact_id import stable_id

from ._mem_store import _MemStore
from ._rwlock import _RWLock


class _ScopeRegistry:
    """Provides entity/connection registry lookups filtered by repo scope.

    Receives the shared _MemStore, RWLock, and an ensure_loaded callback so it
    stays fully in sync with the owning ArtifactIndex without coupling to it.
    """

    def __init__(
        self,
        mem: _MemStore,
        lock: _RWLock,
        ensure_loaded: Callable[[], None],
        scope_fn: Callable[[Path], Literal["enterprise", "engagement", "unknown"]],
    ) -> None:
        self._mem = mem
        self._lock = lock
        self._ensure_loaded = ensure_loaded
        self._scope = scope_fn

    # ── Full ID sets ──────────────────────────────────────────────────────────

    def entity_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return set(self._mem.entities)

    def connection_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return set(self._mem.connections)

    # ── Scope-filtered ID sets ────────────────────────────────────────────────

    def enterprise_entity_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.entities.items() if self._scope(r.path) == "enterprise"}

    def engagement_entity_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.entities.items() if self._scope(r.path) == "engagement"}

    def enterprise_connection_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.connections.items() if self._scope(r.path) == "enterprise"}

    def engagement_connection_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.connections.items() if self._scope(r.path) == "engagement"}

    def enterprise_document_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.documents.items() if self._scope(r.path) == "enterprise"}

    def enterprise_diagram_ids(self) -> set[str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid for aid, r in self._mem.diagrams.items() if self._scope(r.path) == "enterprise"}

    # ── Status and file lookups ───────────────────────────────────────────────

    def entity_status(self, artifact_id: str) -> str | None:
        self._ensure_loaded()
        with self._lock.reading():
            r = self._mem.entities.get(artifact_id)
            return r.status if r is not None else None

    def entity_statuses(self) -> dict[str, str]:
        self._ensure_loaded()
        with self._lock.reading():
            return {aid: r.status for aid, r in self._mem.entities.items()}

    def connection_status(self, artifact_id: str) -> str | None:
        self._ensure_loaded()
        with self._lock.reading():
            r = self._mem.connections.get(artifact_id)
            return r.status if r is not None else None

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        """Resolve any artifact id to its indexed file path, group subdirectory included.

        Honours the port contract for every standalone artifact kind — entities, diagrams,
        and documents — rather than entities alone, so callers resolve a diagram or document
        in a group collection (or other subdirectory) instead of assuming a flat layout.

        Also accepts the short (rename-stable) id form — no trailing ``.slug`` — via
        ``_mem.canonical_id``, the same canonicalization ``ArtifactIndex.read_artifact``/
        ``summarize_artifact`` already apply for reads; every current write-path caller
        (``resolve_diagram_source_path``, entity delete) gets short-id tolerance from this
        one place rather than each needing its own. Deliberately narrower than
        ``canonical_id``'s own general tolerance: a full id whose *slug* is merely stale
        (renamed elsewhere, not just short-form) still misses here — that reconciliation is
        reserved for the explicit ``resolve_artifact``/``artifact_admin_reindex`` path, not
        silently absorbed into ordinary file lookups.
        """
        self._ensure_loaded()
        with self._lock.reading():
            for table in (self._mem.entities, self._mem.diagrams, self._mem.documents):
                r = table.get(artifact_id)
                if r is not None:
                    return r.path
            if stable_id(artifact_id) == artifact_id:
                resolved_id = self._mem.canonical_id(artifact_id)
                if resolved_id != artifact_id:
                    for table in (self._mem.entities, self._mem.diagrams, self._mem.documents):
                        r = table.get(resolved_id)
                        if r is not None:
                            return r.path
            return None
