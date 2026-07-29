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

from collections.abc import Callable
from pathlib import Path

from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS, ANALYSIS_STATUSES, ANALYSIS_UPDATABLE
from src.domain.clock import utc_now_iso as _now_iso
from src.infrastructure.assurance._id_utils import make_analysis_id

# Vocabulary is owned by the domain; re-exported here for adapters that already
# import it from this module.
__all__ = [
    "ANALYSES_DIR",
    "ANALYSIS_METHODS",
    "ANALYSIS_STATUSES",
    "ANALYSIS_UPDATABLE",
    "FileAnalysisStoreMixin",
    "analysis_matches",
    "apply_analysis_update",
    "create_analysis_file",
    "list_analyses_files",
    "new_analysis_record",
    "update_analysis_file",
]

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
    """Apply only updatable fields to ``record`` in place and bump ``updated_at``."""
    for key, value in attrs.items():
        if key in ANALYSIS_UPDATABLE:
            record[key] = value
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
    """

    _repo: Path
    _ANALYSIS_EXT: str = "json"

    def _require_unlocked(self) -> None: ...
    def _read(self, path: Path) -> dict[str, object] | None: ...
    def _write(self, path: Path, data: dict[str, object]) -> None: ...

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
        return self._read(self._analyses_dir() / f"{analysis_id}.{self._ANALYSIS_EXT}")

    def list_analyses(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        self._require_unlocked()
        return list_analyses_files(
            self._read, self._analyses_dir(), self._ANALYSIS_EXT, method=method, status=status
        )

    def update_analysis(self, analysis_id: str, **attrs: object) -> None:
        self._require_unlocked()
        update_analysis_file(
            self._read, self._write, self._analyses_dir(), self._ANALYSIS_EXT, analysis_id, attrs
        )

    def delete_analysis(self, analysis_id: str) -> None:
        self._require_unlocked()
        delete_analysis_file(self._analyses_dir(), self._ANALYSIS_EXT, analysis_id)
