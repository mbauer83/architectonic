"""Factor-assessment persistence, shared by every confidential-store backend.

One shape, three storage mechanisms. Revisions are append-only and superseded revisions are
retained, so a write allocates the next revision number for its (node, factor, basis) key rather
than replacing anything — the previous revision is what shows a reader that a judgement changed
and what it was before.

Reads are batched for a list of node ids. That is a contract rather than an optimisation: a matrix
row needs three factors and a matrix has a row per candidate, so a per-node read would turn one
screen into hundreds of round trips.

Each backend gets a mixin rather than a copy of the logic, following the analysis aggregate's
existing arrangement: the ordering, revision allocation and record shape live here once, and each
mixin supplies only the part that differs — a SQL table, a directory of JSON files, an encrypted
directory, or a REST collection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.domain.clock import utc_now_iso as _now_iso

#: Directory name used by the file-backed backends.
FMEA_ASSESSMENTS_DIR = "fmea-assessments"

#: Collection name used by the REST backend.
FMEA_ASSESSMENTS_COLLECTION = "fmea_factor_assessments"

_FIELDS = ("node_id", "factor", "basis_digest", "revision", "value", "justification", "author", "created_at")


def new_assessment_record(
    *,
    node_id: str,
    factor: str,
    basis_digest: str,
    revision: int,
    value: str,
    justification: str,
    author: str,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "factor": factor,
        "basis_digest": basis_digest,
        "revision": revision,
        "value": value,
        "justification": justification,
        "author": author,
        "created_at": _now_iso(),
    }


def next_revision(existing: Sequence[Mapping[str, object]]) -> int:
    """One past the highest revision for this (node, factor, basis) key.

    Scoped to the key, so a judgement re-made against a *new* basis starts at revision 1: the
    revision counts how often this question was answered against this picture of the model.
    """
    return max((_revision_of(row) for row in existing), default=0) + 1


def _revision_of(row: Mapping[str, object]) -> int:
    """A row's revision number, whatever shape the backend returned it in.

    SQL gives an int, JSON a str or int, a REST payload whatever the server serialized — so the
    value is narrowed here once rather than cast at each of the four call sites.
    """
    return int(str(row.get("revision", 0)))


def sorted_assessments(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Oldest revision first, so a reader follows how a judgement developed."""
    return [dict(row) for row in sorted(rows, key=lambda r: (str(r["factor"]), _revision_of(r)))]


def group_by_node(rows: Sequence[Mapping[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in sorted_assessments(rows):
        grouped.setdefault(str(row["node_id"]), []).append(row)
    return grouped


class SqlFmeaAssessmentMixin:
    """Factor assessments in the `fmea_factor_assessments` table.

    Expects the host store to expose `_conn()` returning an open DB-API connection whose rows
    behave like mappings, and to raise when the store is locked.
    """

    def _conn(self) -> Any:
        raise NotImplementedError("provided by the host store")

    def read_fmea_assessments(self, node_ids: Sequence[str]) -> dict[str, list[dict[str, object]]]:
        ids = tuple(dict.fromkeys(node_ids))
        if not ids:
            return {}
        conn = self._conn()
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT {', '.join(_FIELDS)} FROM fmea_factor_assessments WHERE node_id IN ({placeholders})",
            ids,
        ).fetchall()
        return group_by_node([dict(row) for row in rows])

    def write_fmea_assessment(
        self,
        *,
        node_id: str,
        factor: str,
        basis_digest: str,
        value: str,
        justification: str,
        author: str,
    ) -> dict[str, object]:
        conn = self._conn()
        existing = conn.execute(
            "SELECT revision FROM fmea_factor_assessments "
            "WHERE node_id=? AND factor=? AND basis_digest=?",
            (node_id, factor, basis_digest),
        ).fetchall()
        record = new_assessment_record(
            node_id=node_id,
            factor=factor,
            basis_digest=basis_digest,
            revision=next_revision([dict(row) for row in existing]),
            value=value,
            justification=justification,
            author=author,
        )
        conn.execute(
            f"INSERT INTO fmea_factor_assessments ({', '.join(_FIELDS)}) "
            f"VALUES ({', '.join('?' for _ in _FIELDS)})",
            tuple(record[field] for field in _FIELDS),
        )
        conn.commit()
        return record


class FileFmeaAssessmentMixin:
    """Factor assessments as one file per revision under `fmea-assessments/`.

    Reuses the host store's own `_read`/`_write` pair, so the plain and encrypted variants differ
    only by the file suffix they declare — nothing here needs to know which of the two it is, and
    the encrypted store's records are encrypted by the same code path as its nodes.
    """

    #: File suffix the host store persists with (`.json` plain, `.enc` encrypted).
    _ASSESSMENT_SUFFIX = ".json"

    _repo: Path

    def _require_unlocked(self) -> None:
        raise NotImplementedError("provided by the host store")

    def _read(self, path: Path) -> dict[str, object] | None:
        raise NotImplementedError("provided by the host store")

    def _write(self, path: Path, data: dict[str, object]) -> None:
        raise NotImplementedError("provided by the host store")

    def _assessment_dir(self) -> Path:
        return self._repo / FMEA_ASSESSMENTS_DIR

    def _all_assessments(self) -> list[dict[str, object]]:
        directory = self._assessment_dir()
        if not directory.exists():
            return []
        found: list[dict[str, object]] = []
        for path in sorted(directory.glob(f"*{self._ASSESSMENT_SUFFIX}")):
            record = self._read(path)
            # A directory an operator manages can hold anything; one unreadable file must not take
            # down a read that a person is waiting on.
            if isinstance(record, dict) and "node_id" in record and "revision" in record:
                found.append(record)
        return found

    def read_fmea_assessments(self, node_ids: Sequence[str]) -> dict[str, list[dict[str, object]]]:
        self._require_unlocked()
        wanted = set(node_ids)
        if not wanted:
            return {}
        return group_by_node([r for r in self._all_assessments() if str(r.get("node_id")) in wanted])

    def write_fmea_assessment(
        self,
        *,
        node_id: str,
        factor: str,
        basis_digest: str,
        value: str,
        justification: str,
        author: str,
    ) -> dict[str, object]:
        self._require_unlocked()
        existing = [
            row for row in self._all_assessments()
            if str(row.get("node_id")) == node_id
            and str(row.get("factor")) == factor
            and str(row.get("basis_digest")) == basis_digest
        ]
        record = new_assessment_record(
            node_id=node_id,
            factor=factor,
            basis_digest=basis_digest,
            revision=next_revision(existing),
            value=value,
            justification=justification,
            author=author,
        )
        directory = self._assessment_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"{node_id}__{factor}__{basis_digest}__{record['revision']}"
        self._write(directory / f"{stem}{self._ASSESSMENT_SUFFIX}", record)
        return record


class RestFmeaAssessmentMixin:
    """Factor assessments in a PocketBase collection.

    Expects the host store to expose `_require_unlocked()` returning an HTTP client and
    `_filter(**bindings)` building a parameterized filter. The filter helper is reused rather than
    reimplemented so this cannot become a second, injectable way of querying the same server.
    """

    def _require_unlocked(self) -> Any:
        raise NotImplementedError("provided by the host store")

    def _filter(self, **bindings: str) -> dict[str, str]:
        raise NotImplementedError("provided by the host store")

    def _assessment_url(self) -> str:
        return f"/api/collections/{FMEA_ASSESSMENTS_COLLECTION}/records"

    def read_fmea_assessments(self, node_ids: Sequence[str]) -> dict[str, list[dict[str, object]]]:
        ids = tuple(dict.fromkeys(node_ids))
        if not ids:
            return {}
        client = self._require_unlocked()
        collected: list[dict[str, object]] = []
        # One request per node id: PocketBase's filter grammar has no bound list form, and building
        # an OR chain by string concatenation is the injection surface `_filter` exists to prevent.
        for node_id in ids:
            params: dict[str, str | int] = {"perPage": 500}
            params.update(self._filter(node_id=node_id))
            resp = client.get(self._assessment_url(), params=params)
            resp.raise_for_status()
            collected.extend(resp.json().get("items", []))
        return group_by_node(collected)

    def write_fmea_assessment(
        self,
        *,
        node_id: str,
        factor: str,
        basis_digest: str,
        value: str,
        justification: str,
        author: str,
    ) -> dict[str, object]:
        client = self._require_unlocked()
        params: dict[str, str | int] = {"perPage": 500}
        params.update(self._filter(node_id=node_id, factor=factor, basis_digest=basis_digest))
        resp = client.get(self._assessment_url(), params=params)
        resp.raise_for_status()
        record = new_assessment_record(
            node_id=node_id,
            factor=factor,
            basis_digest=basis_digest,
            revision=next_revision(resp.json().get("items", [])),
            value=value,
            justification=justification,
            author=author,
        )
        created = client.post(self._assessment_url(), json=record)
        created.raise_for_status()
        return record
