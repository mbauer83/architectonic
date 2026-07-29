"""Unit + adapter tests for the assurance analysis aggregate (WU-G5-P1).

Two layers:
  * use-case invariants via an in-memory fake store/archive;
  * a real filesystem adapter (private-git) round-trip proving analysis records
    persist and that nodes are scoped by analysis_id end to end.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application import assurance_analysis as uc
from src.infrastructure.assurance._analysis_records import ANALYSIS_METHODS
from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore


class _FakeArchive:
    def __init__(self) -> None:
        self.appended: list[dict[str, Any]] = []

    def append(self, operation: str, *, node_id: str | None = None,
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {"operation": operation, "node_id": node_id, "payload": payload or {}}
        self.appended.append(entry)
        return entry


class _FakeStore:
    """Minimal in-memory ConfidentialAssuranceStore for analysis use-case tests."""

    def __init__(self, *, unlocked: bool = True) -> None:
        self._unlocked = unlocked
        self.analyses: dict[str, dict[str, Any]] = {}
        self.nodes: list[dict[str, Any]] = []
        self._seq = 0

    def is_unlocked(self) -> bool:
        return self._unlocked

    def create_analysis(self, name: str, method: str, architecture_anchor_id: str,
                        *, tlp: str = "TLP:WHITE", status: str = "draft") -> str:
        self._seq += 1
        analysis_id = f"{method}@{self._seq}"
        self.analyses[analysis_id] = {
            "analysis_id": analysis_id, "name": name, "method": method,
            "architecture_anchor_id": architecture_anchor_id, "status": status, "tlp": tlp,
        }
        return analysis_id

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self.analyses.get(analysis_id)

    def list_analyses(self, *, method: str | None = None,
                     status: str | None = None) -> list[dict[str, Any]]:
        out = list(self.analyses.values())
        if method:
            out = [a for a in out if a["method"] == method]
        if status:
            out = [a for a in out if a["status"] == status]
        return out

    def update_analysis(self, analysis_id: str, **attrs: Any) -> None:
        self.analyses[analysis_id].update(attrs)

    def delete_analysis(self, analysis_id: str) -> None:
        self.analyses.pop(analysis_id, None)

    def list_nodes(self, *, analysis_id: str | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        if analysis_id is None:
            return list(self.nodes)
        return [n for n in self.nodes if n.get("analysis_id") == analysis_id]


# ── create_analysis invariants ──────────────────────────────────────────────────


def test_create_analysis_valid_returns_record_and_audits() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="Brake system safety", method="STPA",
        architecture_anchor_id="APP@123.abc",
    )
    assert isinstance(result, uc.AnalysisOk)
    assert result.payload["method"] == "STPA"
    assert result.payload["architecture_anchor_id"] == "APP@123.abc"
    assert archive.appended[0]["operation"] == "CREATE_ANALYSIS"
    assert archive.appended[0]["node_id"] == result.payload["analysis_id"]


def test_create_analysis_locked_store() -> None:
    store, archive = _FakeStore(unlocked=False), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="x", method="STPA", architecture_anchor_id="APP@1",
    )
    assert isinstance(result, uc.AnalysisLocked)
    assert archive.appended == []


def test_create_analysis_invalid_method() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="x", method="HAZOP", architecture_anchor_id="APP@1",
    )
    assert isinstance(result, uc.AnalysisInvalid)
    assert result.error == "invalid_method"


def test_create_analysis_anchor_is_optional() -> None:
    # Option (B): a single but OPTIONAL anchor. GRC work that spans several
    # systems may omit it; individual nodes still carry their own arch refs.
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(store, archive, name="Q3 controls", method="GRC")
    assert isinstance(result, uc.AnalysisOk)
    assert result.payload["architecture_anchor_id"] == ""


def test_create_analysis_requires_name() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="  ", method="GRC", architecture_anchor_id="APP@1",
    )
    assert isinstance(result, uc.AnalysisInvalid)
    assert result.error == "missing_name"


def test_create_analysis_invalid_status() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="x", method="CAST", architecture_anchor_id="APP@1",
        status="bogus",
    )
    assert isinstance(result, uc.AnalysisInvalid)
    assert result.error == "invalid_status"


@pytest.mark.parametrize("method", ANALYSIS_METHODS)
def test_create_analysis_accepts_each_method(method: str) -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = uc.create_analysis(
        store, archive, name="x", method=method, architecture_anchor_id="APP@1",
    )
    assert isinstance(result, uc.AnalysisOk)


# ── list / get / update ──────────────────────────────────────────────────────────


def test_list_analyses_filters_by_method_and_status() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    uc.create_analysis(store, archive, name="a", method="STPA", architecture_anchor_id="APP@1")
    uc.create_analysis(store, archive, name="b", method="GRC", architecture_anchor_id="APP@2")
    result = uc.list_analyses(store, method="STPA")
    assert isinstance(result, uc.AnalysisOk)
    assert [a["name"] for a in result.payload["analyses"]] == ["a"]


def test_list_analyses_locked() -> None:
    assert isinstance(uc.list_analyses(_FakeStore(unlocked=False)), uc.AnalysisLocked)


def test_get_analysis_not_found() -> None:
    assert isinstance(uc.get_analysis(_FakeStore(), "missing"), uc.AnalysisNotFound)


def test_update_analysis_only_mutates_name_status_tlp() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    created = uc.create_analysis(
        store, archive, name="a", method="STPA", architecture_anchor_id="APP@1",
    )
    assert isinstance(created, uc.AnalysisOk)
    analysis_id = created.payload["analysis_id"]
    # method/anchor are immutable — passing them as kwargs is not accepted by the use case.
    result = uc.update_analysis(store, archive, analysis_id=analysis_id, status="active", name="a2")
    assert isinstance(result, uc.AnalysisOk)
    assert result.payload["status"] == "active"
    assert result.payload["name"] == "a2"
    assert result.payload["method"] == "STPA"
    assert result.payload["architecture_anchor_id"] == "APP@1"
    assert archive.appended[-1]["operation"] == "UPDATE_ANALYSIS"


def test_update_analysis_invalid_status() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    created = uc.create_analysis(
        store, archive, name="a", method="STPA", architecture_anchor_id="APP@1",
    )
    assert isinstance(created, uc.AnalysisOk)
    result = uc.update_analysis(
        store, archive, analysis_id=created.payload["analysis_id"], status="nope",
    )
    assert isinstance(result, uc.AnalysisInvalid)


def test_update_analysis_not_found() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    assert isinstance(
        uc.update_analysis(store, archive, analysis_id="missing", status="active"),
        uc.AnalysisNotFound,
    )


# ── delete ────────────────────────────────────────────────────────────────────────


def test_delete_analysis_empty_succeeds_and_audits() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    aid = store.create_analysis("Abandoned", "STPA", "")
    result = uc.delete_analysis(store, archive, analysis_id=aid)
    assert isinstance(result, uc.AnalysisOk)
    assert result.payload == {"analysis_id": aid, "deleted": True}
    assert store.get_analysis(aid) is None
    assert archive.appended[-1]["operation"] == "DELETE_ANALYSIS"
    assert archive.appended[-1]["node_id"] == aid


def test_delete_analysis_blocks_when_nonempty() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    aid = store.create_analysis("Has nodes", "STPA", "")
    store.nodes.append({"node_id": "HAZ@1", "analysis_id": aid})
    result = uc.delete_analysis(store, archive, analysis_id=aid)
    assert isinstance(result, uc.AnalysisInvalid)
    assert result.error == "analysis_not_empty"
    assert store.get_analysis(aid) is not None  # not deleted
    assert not any(e["operation"] == "DELETE_ANALYSIS" for e in archive.appended)


def test_delete_analysis_not_found() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    assert isinstance(
        uc.delete_analysis(store, archive, analysis_id="missing"),
        uc.AnalysisNotFound,
    )


def test_delete_analysis_locked_store() -> None:
    store, archive = _FakeStore(unlocked=False), _FakeArchive()
    assert isinstance(
        uc.delete_analysis(store, archive, analysis_id="x"),
        uc.AnalysisLocked,
    )


# ── Real adapter round-trip (private-git filesystem store) ────────────────────────


def test_private_git_analysis_roundtrip_and_node_scoping(tmp_path: Any) -> None:
    store = PrivateGitAssuranceStore(tmp_path / "store")
    store.unlock()

    analysis_id = store.create_analysis("Brakes", "STPA", "APP@123.abc")
    record = store.get_analysis(analysis_id)
    assert record is not None
    assert record["method"] == "STPA"
    assert record["architecture_anchor_id"] == "APP@123.abc"
    assert record["created_at"] == record["updated_at"]

    other_id = store.create_analysis("Other", "GRC", "APP@999")

    # Nodes created within an analysis carry its id and are filterable by it.
    n1 = store.create_node("hazard", "H1", analysis_id=analysis_id)
    store.create_node("hazard", "H-other", analysis_id=other_id)
    scoped = store.list_nodes(analysis_id=analysis_id)
    assert [n["node_id"] for n in scoped] == [n1]
    assert store.get_node(n1)["analysis_id"] == analysis_id

    # list_analyses filtering + update.
    assert {a["analysis_id"] for a in store.list_analyses()} == {analysis_id, other_id}
    assert [a["analysis_id"] for a in store.list_analyses(method="GRC")] == [other_id]
    store.update_analysis(analysis_id, status="active")
    assert store.get_analysis(analysis_id)["status"] == "active"
    # update bumps updated_at past created_at is not guaranteed within 1s; just confirm field set.
    assert store.get_analysis(analysis_id)["architecture_anchor_id"] == "APP@123.abc"
