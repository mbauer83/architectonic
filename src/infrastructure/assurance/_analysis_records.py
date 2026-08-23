"""Storage-agnostic shape, vocabulary, and filtering for the assurance analysis aggregate.

An ``AssuranceAnalysis`` is the aggregate root for a unit of STPA/CAST/GRC work:
every assurance node belongs to exactly one analysis (``analysis_id``). An analysis
may optionally name a single system-under-analysis element
(``architecture_anchor_id``); when empty, the analysis spans several systems and
the binding lives only on its individual nodes' architecture references.

This module holds the record shape and pure filter/update helpers shared by the
file-based store adapters; the SQLCipher and PocketBase adapters reuse the
vocabulary constants and the record builder but persist via their own backends.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.assurance.assurance_analysis import (
    ANALYSIS_METHODS,
    ANALYSIS_STATUSES,
    ANALYSIS_UPDATABLE,
    permitted_analysis_updates,
)
from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._id_utils import make_analysis_id

# Vocabulary is owned by the domain; re-exported here for adapters that already
# import it from this module.
__all__ = [
    "ANALYSES_DIR",
    "ANALYSIS_METHODS",
    "ANALYSIS_RECORD_FIELDS",
    "ANALYSIS_STATUSES",
    "ANALYSIS_UPDATABLE",
    "FileAnalysisStoreMixin",
    "analysis_matches",
    "apply_analysis_update",
    "as_analysis_record",
    "create_analysis_file",
    "list_analyses_files",
    "new_analysis_record",
    "update_analysis_file",
]

#: The analysis record, field for field, as every backend must hand it back.
#:
#: It had no single answer before. SQLCipher's ``SELECT *`` returned nine columns; a file-backed
#: record written before it was ever filed had eight, ``group_id`` simply absent; and PocketBase
#: returned its own collection metadata — ``id``, ``collectionId``, ``collectionName``, ``created``,
#: ``updated`` — alongside the eight. The port promises "an analysis record", so a caller that could
#: not know which backend it was talking to could not know what it had, and no closed response
#: contract could be published over it.
ANALYSIS_RECORD_FIELDS: tuple[str, ...] = (
    "analysis_id",
    "group_id",
    "name",
    "method",
    "architecture_anchor_id",
    "status",
    "tlp",
    "created_at",
    "updated_at",
)


def as_analysis_record(row: Mapping[str, object]) -> dict[str, object]:
    """``row`` as the canonical record: exactly :data:`ANALYSIS_RECORD_FIELDS`, nothing else.

    ``group_id`` is the only field a stored row may lack — an unfiled analysis, and every record any
    file-backed store wrote before the field existed — so it reads as ``None`` rather than raising.
    A store is not rewritten to add it: the record on disk stays as it was written, and filing it
    later is what puts a value there.

    A backend's own record identity is dropped here on purpose. It addresses the row inside that
    backend and means nothing outside it, so passing it on would invite a caller to treat one
    store's primary key as this system's.
    """
    missing = [
        field for field in ANALYSIS_RECORD_FIELDS if field != "group_id" and field not in row
    ]
    if missing:
        raise ValueError(f"stored analysis record is missing {', '.join(missing)}")
    return {field: row.get(field) for field in ANALYSIS_RECORD_FIELDS}

#: Directory holding the analysis records in the file-backed stores. Named here rather than
#: spelled at each use site, because filing (`_grouping_records`) has to reach the same records
#: to unfile them and a second spelling of the path is a second thing to keep in step.
ANALYSES_DIR = "analyses"


def new_analysis_record(
    name: str,
    method: str,
    architecture_anchor_id: str = "",
    *,
    tlp: str = "TLP:WHITE",
    status: str = "draft",
) -> dict[str, object]:
    """Build a fully-populated analysis record (id + timestamps assigned here).

    ``architecture_anchor_id`` is optional: an empty string means the analysis is
    not (yet) anchored to a single system-under-analysis element. Individual nodes
    still carry their own architecture references regardless.
    """
    now = _now_iso()
    return {
        "analysis_id": make_analysis_id(method, name),
        # Unfiled: filing is a later gesture, and an analysis is worth recording before anyone has
        # settled where it belongs. Written explicitly so a freshly created record already has the
        # canonical field set rather than acquiring it the first time it is filed.
        "group_id": None,
        "name": name,
        "method": method,
        "architecture_anchor_id": architecture_anchor_id,
        "status": status,
        "tlp": tlp,
        "created_at": now,
        "updated_at": now,
    }


def analysis_matches(
    record: dict[str, object],
    *,
    method: str | None = None,
    status: str | None = None,
) -> bool:
    """Return True if ``record`` passes the active (truthy) filters."""
    if method and record.get("method") != method:
        return False
    return not (status and record.get("status") != status)


def apply_analysis_update(record: dict[str, object], attrs: dict[str, object]) -> dict[str, object]:
    """Apply the fields this update may change to ``record`` in place and bump ``updated_at``.

    Which fields those are is `permitted_analysis_updates`, in the domain, because the SQLCipher
    store decides the same thing when it builds its UPDATE and the two backends must not differ.
    """
    record.update(permitted_analysis_updates(record, attrs))
    record["updated_at"] = _now_iso()
    return record


# ── File-store helpers (shared by private-git and encrypted-private-git) ────────

WriteFn = Callable[[Path, dict[str, object]], None]
ReadFn = Callable[[Path], dict[str, object] | None]


def create_analysis_file(
    write: WriteFn,
    analyses_dir: Path,
    ext: str,
    name: str,
    method: str,
    architecture_anchor_id: str = "",
    *,
    tlp: str,
    status: str,
) -> str:
    record = new_analysis_record(name, method, architecture_anchor_id, tlp=tlp, status=status)
    analysis_id = str(record["analysis_id"])
    write(analyses_dir / f"{analysis_id}.{ext}", record)
    return analysis_id


def list_analyses_files(
    read: ReadFn,
    analyses_dir: Path,
    ext: str,
    *,
    method: str | None,
    status: str | None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for path in sorted(analyses_dir.glob(f"*.{ext}")):
        record = read(path)
        if record is not None and analysis_matches(record, method=method, status=status):
            out.append(record)
    return out


def update_analysis_file(
    read: ReadFn,
    write: WriteFn,
    analyses_dir: Path,
    ext: str,
    analysis_id: str,
    attrs: dict[str, object],
) -> None:
    path = analyses_dir / f"{analysis_id}.{ext}"
    record = read(path)
    if record is None:
        raise RuntimeError(f"Analysis not found: {analysis_id}")
    write(path, apply_analysis_update(record, attrs))


def delete_analysis_file(
    analyses_dir: Path,
    ext: str,
    analysis_id: str,
) -> None:
    (analyses_dir / f"{analysis_id}.{ext}").unlink(missing_ok=True)


class FileAnalysisStoreMixin:
    """Shared analysis CRUD for file-tree assurance stores.

    The host store provides ``_repo``, ``_require_unlocked``, ``_read``, ``_write``
    and sets ``_ANALYSIS_EXT`` (the per-store file extension, e.g. ``json``/``enc``).

    It must also mix in ``FileGroupingStoreMixin``: deleting an analysis has to sweep the
    participation rows naming it, and that mixin owns the member-file naming. Both file-backed
    stores already mix in both.
    """

    _repo: Path
    _ANALYSIS_EXT: str = "json"

    def _require_unlocked(self) -> None: ...
    def _read(self, path: Path) -> dict[str, object] | None: ...
    def _write(self, path: Path, data: dict[str, object]) -> None: ...

    if TYPE_CHECKING:
        # Implemented by FileGroupingStoreMixin, which sits *after* this one in every host's MRO —
        # so the declaration is type-checking-only. A runtime stub here would shadow the real
        # implementation and silently sweep nothing, which is the bug this method exists to fix.
        def remove_all_analysis_members_of_analysis(self, analysis_id: str) -> None: ...

    def _analyses_dir(self) -> Path:
        return self._repo / ANALYSES_DIR

    def create_analysis(
        self,
        name: str,
        method: str,
        architecture_anchor_id: str = "",
        *,
        tlp: str = "TLP:WHITE",
        status: str = "draft",
    ) -> str:
        self._require_unlocked()
        return create_analysis_file(
            self._write, self._analyses_dir(), self._ANALYSIS_EXT,
            name, method, architecture_anchor_id, tlp=tlp, status=status,
        )

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None:
        self._require_unlocked()
        record = self._read(self._analyses_dir() / f"{analysis_id}.{self._ANALYSIS_EXT}")
        return None if record is None else as_analysis_record(record)

    def list_analyses(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        return [
            as_analysis_record(record)
            for record in list_analyses_files(
                self._read, self._analyses_dir(), self._ANALYSIS_EXT, method=method, status=status
            )
        ]

    def update_analysis(self, analysis_id: str, **attrs: object) -> None:
        self._require_unlocked()
        update_analysis_file(
            self._read, self._write, self._analyses_dir(), self._ANALYSIS_EXT, analysis_id, attrs
        )

    def delete_analysis(self, analysis_id: str) -> None:
        """Delete the analysis record and the participation rows naming it.

        Both together, and the participation rows first: interrupted after the analysis file is
        gone, a retry could not find the analysis to know which rows to sweep. Provided by the
        grouping mixin, which owns the member-file naming — every store that mixes this one in
        mixes that one too, so a store cannot delete by a convention that has drifted from the one
        it wrote with.
        """
        self._require_unlocked()
        self.remove_all_analysis_members_of_analysis(analysis_id)
        delete_analysis_file(self._analyses_dir(), self._ANALYSIS_EXT, analysis_id)
