"""Stable-id multimap query and per-entity on-demand reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.application.ports import Candidate
from src.application.repo_path_helpers import all_model_roots
from src.domain.artifact_id import stable_id

from ._mem_store import _MemStore
from ._rwlock import _RWLock


class _IdentityResolver:
    def __init__(
        self,
        mem: _MemStore,
        lock: _RWLock,
        ensure_loaded: Callable[[], None],
        scope_fn: Callable[[Path], str],
    ) -> None:
        self._mem = mem
        self._lock = lock
        self._ensure_loaded = ensure_loaded
        self._scope = scope_fn

    def find_all_by_stable_id(self, short: str) -> list[Candidate]:
        self._ensure_loaded()
        with self._lock.reading():
            return list(self._mem.identity_candidates.get(short, []))

    def scan_duplicates(self) -> dict[str, list[Path]]:
        """Return short ids that map to >1 distinct existing file *within one scope*.

        Cross-scope copies (e.g. an entity promoted into the enterprise repo) are a
        legitimate state and are not reported; two distinct files for the same stable
        id inside a single mount is the rename/shadowing incident and must fail closed.
        """
        self._ensure_loaded()
        with self._lock.reading():
            items = list(self._mem.identity_candidates.items())
        duplicates: dict[str, list[Path]] = {}
        for short, candidates in items:
            by_scope: dict[str, list[Path]] = {}
            for candidate in candidates:
                if not candidate.path.exists():
                    continue
                paths = by_scope.setdefault(candidate.scope, [])
                if candidate.path not in paths:
                    paths.append(candidate.path)
            for paths in by_scope.values():
                if len(paths) > 1:
                    duplicates[short] = paths
        return duplicates

    def reconcile_short_id(
        self,
        short: str,
        apply_file_changes: Callable[[list[Path]], object],
        repo_roots: list[Path],
    ) -> None:
        self._ensure_loaded()
        disk_paths = [
            p
            for root in repo_roots
            for mr in all_model_roots(root)
            for p in mr.rglob(f"{short}*.md")
        ]
        with self._lock.reading():
            indexed_paths = [
                candidate.path
                for candidate in self._mem.identity_candidates.get(short, [])
            ]
        paths = list(dict.fromkeys([*indexed_paths, *disk_paths]))
        if paths:
            apply_file_changes(paths)
        with self._lock.writing():
            self._mem.identity_candidates[short] = [
                Candidate(artifact_id=e.artifact_id, path=e.path, scope=self._scope(e.path))  # type: ignore[arg-type]
                for e in self._mem.entities.values()
                if stable_id(e.artifact_id) == short
            ]
