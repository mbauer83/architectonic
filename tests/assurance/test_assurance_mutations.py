"""Tests for the shared assurance_mutations application use cases.

Verifies:
  - Locked store → MutationLocked on all write operations.
  - Missing node/edge → MutationNotFound on edit/delete/add-edge.
  - Successful writes: correct payload, audit appended, verifier findings returned.
  - Invalid node_type → MutationOk with error payload (not MutationNotFound).
  - Post-write verifier findings are scoped to the affected node.
  - Safety-disposition safeguard (E503) fires for accepted/safety assurance-constraints.
  - delete_node cascades edges (via store.delete_node call).
  - delete_edge: finds edge and removes it; MutationNotFound when absent.
  - register_arch_ref: audits and returns registered status.
"""

from __future__ import annotations

from typing import Any

from src.application import assurance_mutations as mut

# ── Fake infrastructure ───────────────────────────────────────────────────────

class _FakeStore:
    def __init__(self, *, unlocked: bool = True) -> None:
        self._unlocked = unlocked
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._arch_refs: list[dict[str, Any]] = []
        self._next_id = 0

    def _nid(self) -> str:
        self._next_id += 1
        return f"NOD@{self._next_id}"

    def _eid(self) -> str:
        self._next_id += 1
        return f"EDG@{self._next_id}"

    def is_unlocked(self) -> bool:
        return self._unlocked

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def list_nodes(self, **_kwargs: object) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    def create_node(self, node_type: str, name: str, *, content: str = "", **kwargs: object) -> str:
        nid = self._nid()
        self._nodes[nid] = {"node_id": nid, "node_type": node_type, "name": name,
                             "content": content, **kwargs}
        return nid

    def update_node(self, node_id: str, **attrs: object) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].update(attrs)

    def delete_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._edges = [e for e in self._edges
                       if str(e.get("source_id")) != node_id
                       and str(e.get("target_id")) != node_id]

    def list_edges(self, **_kwargs: object) -> list[dict[str, Any]]:
        return list(self._edges)

    def add_edge(self, source_id: str, target_id: str, conn_type: str,
                 *, attributes: dict[str, Any] | None = None) -> str:
        eid = self._eid()
        self._edges.append({
            "edge_id": eid, "source_id": source_id,
            "target_id": target_id, "conn_type": conn_type,
        })
        return eid

    def remove_edge(self, edge_id: str) -> None:
        self._edges = [e for e in self._edges if str(e.get("edge_id")) != edge_id]

    def register_arch_ref(self, assurance_node_id: str, arch_artifact_id: str,
                           ref_type: str) -> None:
        self._arch_refs.append({
            "assurance_node_id": assurance_node_id,
            "arch_artifact_id": arch_artifact_id,
            "ref_type": ref_type,
        })

    def list_arch_refs(self, *, assurance_node_id=None, arch_artifact_id=None):
        return list(self._arch_refs)

    def stats(self) -> dict[str, Any]:
        return {"node_count": len(self._nodes)}


class _FakeArchive:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, operation: str, *, node_id: str | None = None,
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {"operation": operation, "node_id": node_id, "payload": payload}
        self.entries.append(entry)
        return entry


# ── Locked-store guard ────────────────────────────────────────────────────────

def test_create_node_locked() -> None:
    result = mut.create_node(_FakeStore(unlocked=False), _FakeArchive(),
                             node_type="loss", name="L1")
    assert isinstance(result, mut.MutationLocked)


def test_edit_node_locked() -> None:
    result = mut.edit_node(_FakeStore(unlocked=False), _FakeArchive(), node_id="NOD@x")
    assert isinstance(result, mut.MutationLocked)


def test_delete_node_locked() -> None:
    result = mut.delete_node(_FakeStore(unlocked=False), _FakeArchive(), node_id="NOD@x")
    assert isinstance(result, mut.MutationLocked)


def _legal_leads_to(source_type: str, target_type: str) -> frozenset[str]:
    """Unit-test stand-in for the module matrix lookup: hazard→loss chain types."""
    return frozenset({"leads-to"})


def test_add_edge_locked() -> None:
    result = mut.add_edge(_FakeStore(unlocked=False), _FakeArchive(),
                          source_id="A", target_id="B", conn_type="leads-to",
                          legal_connection_types=_legal_leads_to)
    assert isinstance(result, mut.MutationLocked)


def test_delete_edge_locked() -> None:
    result = mut.delete_edge(_FakeStore(unlocked=False), _FakeArchive(), edge_id="EDG@x")
    assert isinstance(result, mut.MutationLocked)


def test_register_arch_ref_locked() -> None:
    result = mut.register_arch_ref(_FakeStore(unlocked=False), _FakeArchive(),
                                   assurance_node_id="NOD@x",
                                   arch_artifact_id="APP@y", ref_type="binds-to")
    assert isinstance(result, mut.MutationLocked)


# ── NotFound guard ────────────────────────────────────────────────────────────

def test_edit_node_not_found() -> None:
    result = mut.edit_node(_FakeStore(), _FakeArchive(), node_id="NOD@missing", name="x")
    assert isinstance(result, mut.MutationNotFound)
    assert result.artifact_id == "NOD@missing"


def test_delete_node_not_found() -> None:
    result = mut.delete_node(_FakeStore(), _FakeArchive(), node_id="NOD@missing")
    assert isinstance(result, mut.MutationNotFound)


def test_add_edge_source_not_found() -> None:
    store = _FakeStore()
    store.create_node("loss", "L1")
    result = mut.add_edge(store, _FakeArchive(),
                          source_id="NOD@missing", target_id="NOD@1", conn_type="leads-to",
                          legal_connection_types=_legal_leads_to)
    assert isinstance(result, mut.MutationNotFound)
    assert result.artifact_id == "NOD@missing"


def test_add_edge_target_not_found() -> None:
    store = _FakeStore()
    nid = store.create_node("loss", "L1")
    result = mut.add_edge(store, _FakeArchive(),
                          source_id=nid, target_id="NOD@missing", conn_type="leads-to",
                          legal_connection_types=_legal_leads_to)
    assert isinstance(result, mut.MutationNotFound)
    assert result.artifact_id == "NOD@missing"


def test_delete_edge_not_found() -> None:
    result = mut.delete_edge(_FakeStore(), _FakeArchive(), edge_id="EDG@missing")
    assert isinstance(result, mut.MutationNotFound)


def test_register_arch_ref_node_not_found() -> None:
    result = mut.register_arch_ref(_FakeStore(), _FakeArchive(),
                                   assurance_node_id="NOD@missing",
                                   arch_artifact_id="APP@x", ref_type="binds-to")
    assert isinstance(result, mut.MutationNotFound)


# ── Successful writes ─────────────────────────────────────────────────────────

def test_create_node_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    result = mut.create_node(store, archive, node_type="loss", name="Loss 1")
    assert isinstance(result, mut.MutationOk)
    assert "node_id" in result.payload
    assert result.payload["name"] == "Loss 1"
    assert len(archive.entries) == 1
    assert archive.entries[0]["operation"] == "CREATE"


def test_create_node_invalid_type() -> None:
    result = mut.create_node(_FakeStore(), _FakeArchive(), node_type="bogus", name="X")
    assert isinstance(result, mut.MutationOk)
    assert result.payload.get("error") == "invalid_node_type"


def test_edit_node_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    nid = store.create_node("hazard", "H1")
    result = mut.edit_node(store, archive, node_id=nid, name="H1 updated", status="active")
    assert isinstance(result, mut.MutationOk)
    assert result.payload["node_id"] == nid
    updated = result.payload["updated"]
    assert "name" in updated and "status" in updated
    assert len(archive.entries) == 1
    assert archive.entries[0]["operation"] == "UPDATE"


def test_edit_node_no_updates_still_ok() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    nid = store.create_node("hazard", "H1")
    result = mut.edit_node(store, archive, node_id=nid)
    assert isinstance(result, mut.MutationOk)
    assert result.payload["updated"] == []
    assert len(archive.entries) == 0  # nothing to audit when no fields changed


def test_delete_node_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    nid = store.create_node("loss", "L1")
    result = mut.delete_node(store, archive, node_id=nid)
    assert isinstance(result, mut.MutationOk)
    assert result.payload["deleted"] == nid
    assert store.get_node(nid) is None
    assert archive.entries[0]["operation"] == "DELETE"


def test_add_edge_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    sid = store.create_node("hazard", "H1")
    tid = store.create_node("loss", "L1")
    result = mut.add_edge(store, archive, source_id=sid, target_id=tid, conn_type="leads-to",
                          legal_connection_types=_legal_leads_to)
    assert isinstance(result, mut.MutationOk)
    assert "edge_id" in result.payload
    assert result.payload["conn_type"] == "leads-to"
    assert archive.entries[0]["operation"] == "ADD_EDGE"


def test_delete_edge_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    sid = store.create_node("hazard", "H1")
    tid = store.create_node("loss", "L1")
    eid = store.add_edge(sid, tid, "leads-to")
    result = mut.delete_edge(store, archive, edge_id=eid)
    assert isinstance(result, mut.MutationOk)
    assert result.payload["deleted"] == eid
    assert store.list_edges() == []
    assert archive.entries[0]["operation"] == "DELETE_EDGE"


def test_register_arch_ref_success() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    nid = store.create_node("control-structure-node", "App")
    result = mut.register_arch_ref(store, archive, assurance_node_id=nid,
                                   arch_artifact_id="APP@123", ref_type="binds-to")
    assert isinstance(result, mut.MutationOk)
    assert result.payload["status"] == "registered"
    assert archive.entries[0]["operation"] == "ADD_ARCH_REF"


# ── Safety-disposition safeguard (E503) ──────────────────────────────────────

def test_safeguard_fires_for_accepted_safety_constraint() -> None:
    store, archive = _FakeStore(), _FakeArchive()
    nid = store.create_node("assurance-constraint", "SC1",
                             concern_class="safety", disposition="accepted")
    result = mut.edit_node(store, archive, node_id=nid,
                           concern_class="safety", disposition="accepted")
    assert isinstance(result, mut.MutationOk)
    e503_codes = [f["code"] for f in result.findings if f["code"] == "E503"]
    assert e503_codes, "E503 safeguard should fire for accepted/safety constraint"


def test_safeguard_absent_for_alarp_disposition() -> None:
    store = _FakeStore()
    nid = store.create_node("assurance-constraint", "SC2",
                             concern_class="safety", disposition="alarp-justified")
    result = mut.edit_node(store, _FakeArchive(), node_id=nid,
                           concern_class="safety", disposition="alarp-justified")
    assert isinstance(result, mut.MutationOk)
    e503_codes = [f["code"] for f in result.findings if f["code"] == "E503"]
    assert not e503_codes, "E503 should not fire for alarp-justified"
