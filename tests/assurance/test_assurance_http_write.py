"""Tests for assurance HTTP write endpoints.

Verifies:
  - Locked store → 423 on every write endpoint.
  - create_node: 200 with node_id; invalid type returns error payload.
  - edit_node: 200 on success; 404 for missing node.
  - delete_node: 200 with deleted key; 404 for missing node.
  - add_edge: 200 with edge_id; 404 for missing source/target.
  - delete_edge: 200 with deleted key; 404 for missing edge.
  - seal_baseline: 200 when unlocked; 423 when locked.
  - register_arch_ref: 200 on success.
  - model_this: 200 (spec only, no state); 409 for wrong binding_status.
  - All responses carry Cache-Control: no-store.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

httpx = pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from tests.support.api_app import build_api_app  # noqa: E402

# ── Fake infrastructure (extended from read tests) ────────────────────────────

#: The analysis the fixtures attribute their nodes to. This fake mints nodes *unattributed*,
#: because the provenance state-machine tests need that state; every other fixture passes this id
#: explicitly, since an unattributed node is repair-only.
_FIXTURE_ANALYSIS = "STPA@7"


class _FakeStore:
    def __init__(self, *, unlocked: bool = True) -> None:
        self._unlocked = unlocked
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._next = 0
        self._arch_refs: list[dict[str, Any]] = []
        # Every node is created inside an analysis now, so the fake has to have one.
        self._analyses: dict[str, dict[str, Any]] = {
            _FIXTURE_ANALYSIS: {
                "analysis_id": _FIXTURE_ANALYSIS, "name": "Brakes", "method": "STPA",
            },
        }

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self._analyses.get(analysis_id)

    def _nid(self) -> str:
        self._next += 1
        return f"NOD@{self._next}"

    def is_unlocked(self) -> bool:
        return self._unlocked

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def list_nodes(self, **_kwargs: object) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    def create_node(self, node_type: str, name: str, *, content: str = "",
                    **kwargs: object) -> str:
        nid = self._nid()
        self._nodes[nid] = {"node_id": nid, "node_type": node_type, "name": name, **kwargs}
        return nid

    def update_node(self, node_id: str, **attrs: object) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].update(attrs)

    def delete_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    def list_edges(self, **_kwargs: object) -> list[dict[str, Any]]:
        return list(self._edges)

    def add_edge(self, source_id: str, target_id: str, conn_type: str,
                 *, attributes: dict[str, Any] | None = None) -> str:
        self._next += 1
        eid = f"EDG@{self._next}"
        self._edges.append({
            "edge_id": eid, "source_id": source_id,
            "target_id": target_id, "conn_type": conn_type,
        })
        return eid

    def remove_edge(self, edge_id: str) -> None:
        self._edges = [e for e in self._edges if str(e.get("edge_id")) != edge_id]

    def register_arch_ref(self, *_args: object, **_kwargs: object) -> None:
        pass

    def list_arch_refs(self, *, assurance_node_id=None, arch_artifact_id=None):
        return list(self._arch_refs)

    def stats(self) -> dict[str, Any]:
        return {}

    def search_nodes(self, q: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return []


class _FakeArchive:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, operation: str, *, node_id: str | None = None,
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
        e = {"operation": operation}
        self.entries.append(e)
        return e

    def seal_baseline(self, *, notes: str = "",
                      analysis_id: str | None = None) -> dict[str, Any]:
        return {"sealed": True, "notes": notes}

    def list_baselines(self) -> list[Any]:
        return []


class _FakeContext:
    def __init__(self, store: _FakeStore, ceiling: str = "TLP:RED") -> None:
        self._store = store
        self._archive = _FakeArchive()
        self.max_classification = ceiling

    @property
    def store(self) -> _FakeStore:
        return self._store

    @property
    def archive(self) -> _FakeArchive:
        return self._archive

    def is_available(self) -> bool:
        return self._store.is_unlocked()

    def locked_response(self) -> dict[str, Any]:
        return {"error": "assurance_store_locked", "message": "locked"}

    def not_found_response(self, node_id: str) -> dict[str, Any]:
        return {"error": "not_found", "node_id": node_id}


# ── Client factory ─────────────────────────────────────────────────────────────

_CTX_PATH = "src.infrastructure.gui.routers._assurance_write.get_assurance_context"
_CTX_PATH_READ = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"


def _make_client(ctx: _FakeContext) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    client = TestClient(build_api_app(router), raise_server_exceptions=False)
    for path in (_CTX_PATH, _CTX_PATH_READ):
        p = patch(path, return_value=ctx)
        p.start()
    return client


# ── 423 locked on every write ──────────────────────────────────────────────────

@pytest.mark.parametrize("method,url,body", [
    ("POST", f"/api/assurance/analyses/{_FIXTURE_ANALYSIS}/nodes", {"node_type": "loss", "name": "L"}),
    ("PUT", "/api/assurance/nodes/x/provenance", {"analysis_id": "STPA@7"}),
    ("PATCH", "/api/assurance/nodes/x", {"name": "y"}),
    ("DELETE", "/api/assurance/nodes/x", None),
    ("POST", "/api/assurance/edges", {"source_id": "A", "target_id": "B", "conn_type": "leads-to"}),
    ("DELETE", "/api/assurance/edges/x", None),
    ("POST", "/api/assurance/baselines", {}),
    ("POST", "/api/assurance/arch-refs",
     {"assurance_node_id": "A", "arch_artifact_id": "B", "ref_type": "binds-to"}),
])
def test_locked_returns_423(method: str, url: str, body: dict[str, Any] | None) -> None:
    ctx = _FakeContext(_FakeStore(unlocked=False))
    client = _make_client(ctx)
    if body is None:
        resp = getattr(client, method.lower())(url)
    else:
        resp = getattr(client, method.lower())(url, json=body)
    assert resp.status_code == 423
    assert resp.headers.get("cache-control") == "no-store"


# ── create_node ────────────────────────────────────────────────────────────────

def test_create_node_success() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.post(
        f"/api/assurance/analyses/{_FIXTURE_ANALYSIS}/nodes", json={"node_type": "loss", "name": "L1"})
    assert resp.status_code == 200
    body = resp.json()
    assert "node_id" in body
    assert body["name"] == "L1"
    assert resp.headers.get("cache-control") == "no-store"


def test_create_node_invalid_type_error_payload() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.post(
        f"/api/assurance/analyses/{_FIXTURE_ANALYSIS}/nodes", json={"node_type": "bogus", "name": "X"})
    assert resp.status_code == 200  # use case returns MutationOk with error payload
    assert resp.json()["error"] == "invalid_node_type"


def test_a_node_records_the_analysis_it_was_created_in() -> None:
    """Provenance comes from the path, so there is no way to create a node without it.

    It used to be an optional body field, which is how 26 nodes came to sit in the store with no
    author recorded — the field was simply omitted and nothing objected.
    """
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post(
        f"/api/assurance/analyses/{_FIXTURE_ANALYSIS}/nodes", json={"node_type": "hazard", "name": "H1"})
    assert resp.status_code == 200
    nid = resp.json()["node_id"]
    assert store.get_node(nid)["analysis_id"] == "STPA@7"


def test_a_create_body_naming_its_own_analysis_is_rejected() -> None:
    """The path already says which analysis. A body that said so too would give a caller two
    places to disagree about what produced the node."""
    client = _make_client(_FakeContext(_FakeStore()))
    resp = client.post(f"/api/assurance/analyses/{_FIXTURE_ANALYSIS}/nodes", json={
        "node_type": "hazard", "name": "H1", "analysis_id": "STPA@7",
    })
    assert resp.status_code == 422


def test_a_node_cannot_be_created_in_an_analysis_that_does_not_exist() -> None:
    client = _make_client(_FakeContext(_FakeStore()))
    resp = client.post(
        "/api/assurance/analyses/AN@nope/nodes", json={"node_type": "hazard", "name": "H1"})
    assert resp.status_code == 404


class TestProvenanceStateMachine:
    """The one audited path that may set provenance, and the transitions it permits.

    Immutability is the whole point: an analysis's output is a historical fact, and a node that
    could move between analyses would rewrite what each of them is on record as having found. The
    single legitimate transition is repairing a node that has none.
    """

    def _client_and_store(self) -> tuple[Any, Any]:
        store = _FakeStore()
        store._analyses["STPA@8"] = {  # noqa: SLF001
            "analysis_id": "STPA@8", "name": "Other", "method": "STPA",
        }
        return _make_client(_FakeContext(store)), store

    def test_an_unattributed_node_can_be_repaired(self) -> None:
        client, store = self._client_and_store()
        nid = store.create_node("hazard", "H1")

        resp = client.put(f"/api/assurance/nodes/{nid}/provenance", json={"analysis_id": "STPA@7"})

        assert resp.status_code == 204
        assert resp.content == b""
        assert store.get_node(nid)["analysis_id"] == "STPA@7"

    def test_re_asserting_the_same_analysis_is_idempotent(self) -> None:
        client, store = self._client_and_store()
        nid = store.create_node("hazard", "H1")
        url = f"/api/assurance/nodes/{nid}/provenance"

        assert client.put(url, json={"analysis_id": "STPA@7"}).status_code == 204
        assert client.put(url, json={"analysis_id": "STPA@7"}).status_code == 204
        assert store.get_node(nid)["analysis_id"] == "STPA@7"

    def test_reattribution_to_another_analysis_is_refused(self) -> None:
        client, store = self._client_and_store()
        nid = store.create_node("hazard", "H1")
        client.put(f"/api/assurance/nodes/{nid}/provenance", json={"analysis_id": "STPA@7"})

        resp = client.put(
            f"/api/assurance/nodes/{nid}/provenance", json={"analysis_id": "STPA@8"})

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "provenance_immutable"
        assert detail["details"]["current_analysis_id"] == "STPA@7"
        assert store.get_node(nid)["analysis_id"] == "STPA@7"

    def test_provenance_cannot_be_withdrawn_through_the_edit_contract(self) -> None:
        """``analysis_id`` left the edit DTO, so a caller still sending it is told rather than
        silently re-attributing the node."""
        client, store = self._client_and_store()
        nid = store.create_node("hazard", "H1")
        client.put(f"/api/assurance/nodes/{nid}/provenance", json={"analysis_id": "STPA@7"})

        resp = client.patch(f"/api/assurance/nodes/{nid}", json={"analysis_id": "STPA@8"})

        assert resp.status_code == 422
        assert store.get_node(nid)["analysis_id"] == "STPA@7"

    def test_an_analysis_that_does_not_exist_is_not_a_repair(self) -> None:
        client, store = self._client_and_store()
        nid = store.create_node("hazard", "H1")

        resp = client.put(
            f"/api/assurance/nodes/{nid}/provenance", json={"analysis_id": "AN@nope"})

        assert resp.status_code == 404
        assert not store.get_node(nid).get("analysis_id")


# ── edit_node ──────────────────────────────────────────────────────────────────

def test_edit_node_success() -> None:
    store = _FakeStore()
    nid = store.create_node("hazard", "H1", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.patch(f"/api/assurance/nodes/{nid}", json={"name": "H1 updated"})
    assert resp.status_code == 200
    assert resp.json()["node_id"] == nid


def test_edit_node_not_found() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.patch("/api/assurance/nodes/NOD@missing", json={"name": "x"})
    assert resp.status_code == 404


# ── delete_node ────────────────────────────────────────────────────────────────

def test_delete_node_success() -> None:
    store = _FakeStore()
    nid = store.create_node("loss", "L1", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.delete(f"/api/assurance/nodes/{nid}")
    # 204 and no body: a deletion has nothing to describe, and the id it removed is the one the
    # caller just addressed. `no-store` rides on it anyway — the confidentiality contract covers
    # every response this surface makes, not only the ones carrying a body.
    assert resp.status_code == 204
    assert resp.content == b""
    assert resp.headers["Cache-Control"] == "no-store"
    assert store.get_node(nid) is None


def test_delete_node_not_found() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.delete("/api/assurance/nodes/NOD@gone")
    assert resp.status_code == 404


# ── add_edge ───────────────────────────────────────────────────────────────────

def test_add_edge_success() -> None:
    store = _FakeStore()
    sid = store.create_node("hazard", "H1", analysis_id=_FIXTURE_ANALYSIS)
    tid = store.create_node("loss", "L1", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/edges", json={
        "source_id": sid, "target_id": tid, "conn_type": "leads-to",
    })
    assert resp.status_code == 200
    assert "edge_id" in resp.json()


def test_add_edge_illegal_pair_is_a_422_typed_envelope() -> None:
    store = _FakeStore()
    sid = store.create_node("loss", "L1", analysis_id=_FIXTURE_ANALYSIS)
    tid = store.create_node("hazard", "H1", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/edges", json={
        "source_id": sid, "target_id": tid, "conn_type": "leads-to",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "illegal_connection_type"
    assert body["source_type"] == "loss"
    assert body["target_type"] == "hazard"
    assert body["conn_type"] == "leads-to"
    assert isinstance(body["legal_types"], list)
    assert store.list_edges() == []  # nothing written


def test_add_edge_source_not_found() -> None:
    store = _FakeStore()
    tid = store.create_node("loss", "L1", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/edges", json={
        "source_id": "NOD@missing", "target_id": tid, "conn_type": "leads-to",
    })
    assert resp.status_code == 404


# ── delete_edge ────────────────────────────────────────────────────────────────

def test_delete_edge_success() -> None:
    store = _FakeStore()
    sid = store.create_node("hazard", "H1", analysis_id=_FIXTURE_ANALYSIS)
    tid = store.create_node("loss", "L1", analysis_id=_FIXTURE_ANALYSIS)
    eid = store.add_edge(sid, tid, "leads-to")
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.delete(f"/api/assurance/edges/{eid}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert resp.headers["Cache-Control"] == "no-store"


def test_delete_edge_not_found() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.delete("/api/assurance/edges/EDG@missing")
    assert resp.status_code == 404


# ── seal_baseline ──────────────────────────────────────────────────────────────

def test_seal_baseline_success() -> None:
    ctx = _FakeContext(_FakeStore())
    client = _make_client(ctx)
    resp = client.post("/api/assurance/baselines", json={"notes": "test"})
    assert resp.status_code == 200
    assert resp.json()["sealed"] is True


# ── register_arch_ref ─────────────────────────────────────────────────────────

def test_register_arch_ref_success() -> None:
    store = _FakeStore()
    nid = store.create_node("control-structure-node", "App", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/arch-refs", json={
        "assurance_node_id": nid,
        "arch_artifact_id": "APP@123",
        "ref_type": "binds-to",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "registered"


# ── model_this ────────────────────────────────────────────────────────────────

def test_model_this_separation_of_duties_returns_task_spec() -> None:
    store = _FakeStore()
    nid = store.create_node("control-structure-node", "X",
                             binding_status="unbound-pending",
                             analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/model-this", json={
        "assurance_node_id": nid,
        "suggested_arch_type": "application-component",
        "suggested_name": "X Component",
        "separation_of_duties": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "task_required"
    assert body["action_required"] == "create_arch_entity_then_bind"
    assert body["assurance_node_id"] == nid


def test_model_this_default_creates_and_binds() -> None:
    # Default path uses the architecture-write creator → Bound. Patch the creator
    # so the test does not touch the real backend write path.
    store = _FakeStore()
    nid = store.create_node("control-structure-node", "X",
                             binding_status="unbound-pending",
                             analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)

    class _StubCreator:
        def is_known_type(self, artifact_type: str) -> bool:
            return True

        def create(self, artifact_type: str, name: str) -> str:
            return "APP@9.bound"

    with patch(
        "src.infrastructure.gui.routers._assurance_write.GuiArchitectureEntityCreator",
        _StubCreator,
    ):
        resp = client.post("/api/assurance/model-this", json={
            "assurance_node_id": nid,
            "suggested_arch_type": "application-component",
            "suggested_name": "X Component",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "bound"
    assert body["arch_artifact_id"] == "APP@9.bound"
    assert store.get_node(nid)["binding_status"] == "bound"


def test_model_this_wrong_binding_status_returns_409() -> None:
    store = _FakeStore()
    nid = store.create_node("control-structure-node", "Y", binding_status="bound", analysis_id=_FIXTURE_ANALYSIS)
    ctx = _FakeContext(store)
    client = _make_client(ctx)
    resp = client.post("/api/assurance/model-this", json={
        "assurance_node_id": nid,
        "suggested_arch_type": "application-component",
        "suggested_name": "Y Component",
    })
    assert resp.status_code == 409
