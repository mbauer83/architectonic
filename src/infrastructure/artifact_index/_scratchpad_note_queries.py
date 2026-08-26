"""Reading the scratchpads, and the notes on them, that the index holds.

Its own mixin for the reason `_ReverseReferenceQueries` is one: `service.py` is at the source-length
policy's recorded ceiling, and a new record kind arrives as a pair of readers that belong together
and to nothing else.

A note is *findable*, not addressable — it belongs to the search protocol rather than the lookup
one, because the verifier and the registry read artifacts and a note is part of one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.domain.ontology_representation.artifact_types import ScratchpadNoteRecord, ScratchpadRecord

if TYPE_CHECKING:
    from ._mem_store import _MemStore
    from ._rwlock import _RWLock


class _IndexInternals(Protocol):
    _mem: "_MemStore"
    _lock: "_RWLock"

    def _ensure_loaded(self) -> None: ...


class _ScratchpadNoteQueries:
    """Mixed into `ArtifactIndex`, which supplies the memory store, the lock and the load latch."""

    def get_scratchpad(self: _IndexInternals, artifact_id: str) -> ScratchpadRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.scratchpad(artifact_id)

    def list_scratchpads_indexed(
        self: _IndexInternals, *, status: str | None = None, group: str | None = None
    ) -> list[ScratchpadRecord]:
        """The pads the index holds.

        Named apart from the scratchpad *service*'s `list_scratchpads`, which reads the files and
        answers the authoring surface. This one answers search, from the same rows search ranks, and
        two functions with one name answering from two sources is the confusion worth a longer name.
        """
        self._ensure_loaded()
        with self._lock.reading():
            found = [
                record
                for record in self._mem.scratchpads.values()
                if (status is None or record.status == status)
                and (group is None or record.group == group)
            ]
        return sorted(found, key=lambda record: record.artifact_id)

    def get_scratchpad_note(self: _IndexInternals, artifact_id: str) -> ScratchpadNoteRecord | None:
        self._ensure_loaded()
        with self._lock.reading():
            return self._mem.scratchpad_note(artifact_id)

    def list_scratchpad_notes(
        self: _IndexInternals,
        *,
        scratchpad_id: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ScratchpadNoteRecord]:
        self._ensure_loaded()
        with self._lock.reading():
            found = [
                record
                for record in self._mem.scratchpad_notes.values()
                if (scratchpad_id is None or record.scratchpad_id == scratchpad_id)
                and (status is None or record.status == status)
                and (group is None or record.group == group)
            ]
        return sorted(found, key=lambda record: record.artifact_id)
