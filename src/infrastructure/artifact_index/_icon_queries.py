"""Reading the shared icons the index holds.

A mixin for the reason `_ScratchpadNoteQueries` is one: `service.py` is at the source-length ceiling,
and a record kind arrives as a pair of readers that belong together. Filtering — by what an icon
applies to, by tag, by name — is the picker's, in the application layer; the index answers with
what it holds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.domain.icons.icon_record import IconRecord

if TYPE_CHECKING:
    from ._mem_store import _MemStore
    from ._rwlock import _RWLock


class _IndexInternals(Protocol):
    _mem: "_MemStore"
    _lock: "_RWLock"

    def _ensure_loaded(self) -> None: ...


class _IconQueries:
    """Mixed into `ArtifactIndex`, which supplies the memory store, the lock and the load latch."""

    def get_icon(self: _IndexInternals, artifact_id: str) -> IconRecord | None:
        """The icon under any id form — short, stale-slug or full; the engagement's when both hold it."""
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.icon(artifact_id)

    def list_icons(self: _IndexInternals) -> list[IconRecord]:
        self._ensure_loaded()
        with self._lock.reading():
            return sorted(self._mem.icons.values(), key=lambda record: record.artifact_id)
