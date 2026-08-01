"""Safety tests for WU-G3 assurance search.

Verifies:
  - No new unencrypted files are created on disk after calling search_nodes.
  - Concurrent read threads all complete without error.
  - search_nodes: limit, empty query, case-insensitive matching.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


# ── Fixture: real SQLCipher store in a tmpdir ─────────────────────────────────

@pytest.fixture()
def store(tmp_path: Path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "search_safety.db"
    init_store(db_path)
    s = SQLCipherAssuranceStore(db_path)
    s.unlock()
    s.create_node("loss", "Loss of Control Authority", tlp="TLP:WHITE", content="safety critical loss")
    s.create_node("hazard", "Navigation Hazard", tlp="TLP:WHITE", content="obstacle detection hazard")
    s.create_node("risk", "SECRET Risk", tlp="TLP:RED", content="classified risk content")
    yield s
    s.lock()


# ── No-plaintext-file test ────────────────────────────────────────────────────

def _snapshot_files(root: Path) -> frozenset[Path]:
    return frozenset(p for p in root.rglob("*") if p.is_file()) if root.exists() else frozenset()


def test_search_nodes_creates_no_new_files(store: Any, tmp_path: Path) -> None:
    """search_nodes must not write any new files to the store directory."""
    before = _snapshot_files(tmp_path)

    store.search_nodes("loss")
    store.search_nodes("Hazard")
    store.search_nodes("nonexistent_xyz")

    after = _snapshot_files(tmp_path)
    new_files = after - before
    assert not new_files, f"Unexpected new files after search: {new_files}"


def test_search_nodes_no_new_files_in_assurance_dir(store: Any) -> None:
    """search_nodes must not write files into the project .arch-assurance tree."""
    project_root = Path(__file__).resolve().parents[2]
    arch_assurance = project_root / ".arch-assurance"
    before = _snapshot_files(arch_assurance)

    store.search_nodes("loss", limit=5)

    after = _snapshot_files(arch_assurance)
    new_files = after - before
    assert not new_files, f"Unexpected files in .arch-assurance after search: {new_files}"


# ── Concurrent read test (HTTP layer) ────────────────────────────────────────

def test_concurrent_search_via_http_completes() -> None:
    """Concurrent HTTP search requests must all complete and return valid JSON.

    This tests the actual concurrent access path (FastAPI HTTP layer with
    _FakeStore), which is the real server pattern. Direct SQLCipher connections
    are thread-bound by SQLite design; the HTTP layer serializes store access.
    """
    from unittest.mock import patch

    from starlette.testclient import TestClient

    from src.infrastructure.rest.routers.assurance.router import router

    class _ThreadSafeStore:
        """Simple dict-backed store safe for concurrent HTTP handler calls."""
        def is_unlocked(self) -> bool:
            return True

        def list_nodes(self, **_kw):
            return [
                {"node_id": "LSS@n1", "node_type": "loss",
                 "name": "Alpha loss", "tlp": "TLP:WHITE", "status": "draft"},
                {"node_id": "HAZ@n2", "node_type": "hazard",
                 "name": "Beta hazard", "tlp": "TLP:WHITE", "status": "draft"},
            ]

        def search_nodes(self, query: str, *, limit: int = 20):
            q = query.lower()
            return [n for n in self.list_nodes() if q in n["name"].lower()][:limit]

        def get_node(self, node_id: str):
            return next((n for n in self.list_nodes() if n["node_id"] == node_id), None)

        def list_edges(self, **_kw):
            return []

        def list_arch_refs(self, **_kw):
            return []

        def list_analyses(self, *, method=None, status=None):
            return []

        def list_participating_analyses(self, node_id):
            return []

        def stats(self):
            return {"node_count": 2, "edge_count": 0, "by_type": {}}

    class _FakeCtx:
        max_classification = "TLP:RED"
        store = _ThreadSafeStore()
        archive = type("A", (), {"list_baselines": lambda self: []})()

        def is_available(self) -> bool:
            return True

    ctx = _FakeCtx()
    app = build_api_app(router)
    client = TestClient(app, raise_server_exceptions=False)

    errors: list[str] = []
    statuses: list[int] = []
    lock = threading.Lock()

    def _worker(query: str) -> None:
        try:
            r = client.get(f"/api/assurance/search?q={query}")
            with lock:
                statuses.append(r.status_code)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(str(exc))

    queries = ["Alpha", "Beta", "loss", "hazard", "xyz"] * 4
    threads = [threading.Thread(target=_worker, args=(q,)) for q in queries]
    # Patch the shared context ONCE around the whole thread lifecycle. Patching
    # per-thread races: unittest.mock.patch mutates a module global, so one
    # thread's __exit__ can restore the real (locked) context while another is
    # mid-request, yielding a spurious 423. The target is read-only here.
    with patch(
        "src.infrastructure.rest.routers.assurance._read.get_assurance_context",
        return_value=ctx,
    ):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

    assert not errors, f"Thread errors: {errors}"
    assert all(s == 200 for s in statuses), f"Non-200 statuses: {statuses}"


# ── Store-level: search behaviours ────────────────────────────────────────────

def test_search_nodes_respects_limit(store: Any) -> None:
    hits = store.search_nodes("a", limit=1)
    assert len(hits) <= 1


def test_search_nodes_name_match(store: Any) -> None:
    hits = store.search_nodes("Loss of Control", limit=10)
    assert any("Loss of Control Authority" in str(h.get("name", "")) for h in hits)


def test_search_nodes_content_match(store: Any) -> None:
    hits = store.search_nodes("obstacle detection", limit=10)
    assert len(hits) == 1
    assert str(hits[0].get("node_type", "")) == "hazard"


def test_search_nodes_no_match_returns_empty(store: Any) -> None:
    hits = store.search_nodes("ZQXWVUTSRPONMLKJIHGFEDCBA_no_match", limit=10)
    assert hits == []


def test_search_nodes_case_insensitive(store: Any) -> None:
    lower = store.search_nodes("loss of control", limit=10)
    upper = store.search_nodes("LOSS OF CONTROL", limit=10)
    assert {str(h["node_id"]) for h in lower} == {str(h["node_id"]) for h in upper}
    assert len(lower) >= 1
