"""Integration tests for the SQLCipher assurance store."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    s = SQLCipherAssuranceStore(db_path)
    s.unlock()
    yield s
    s.lock()


def test_unlock_and_lock(store) -> None:  # type: ignore[no-untyped-def]
    assert store.is_unlocked()
    store.lock()
    assert not store.is_unlocked()
    store.unlock()
    assert store.is_unlocked()


def test_create_and_get_node(store) -> None:  # type: ignore[no-untyped-def]
    node_id = store.create_node("loss", "Loss of Vehicle Control", concern_class="safety")
    assert node_id.startswith("LSS@")
    node = store.get_node(node_id)
    assert node is not None
    assert node["node_type"] == "loss"
    assert node["name"] == "Loss of Vehicle Control"
    assert node["concern_class"] == "safety"


def test_list_nodes_filter_by_type(store) -> None:  # type: ignore[no-untyped-def]
    store.create_node("loss", "Loss A", concern_class="safety")
    store.create_node("hazard", "Hazard B", concern_class="security")
    losses = store.list_nodes(node_type="loss")
    hazards = store.list_nodes(node_type="hazard")
    assert all(n["node_type"] == "loss" for n in losses)
    assert all(n["node_type"] == "hazard" for n in hazards)


def test_update_node(store) -> None:  # type: ignore[no-untyped-def]
    node_id = store.create_node("loss", "Loss A")
    store.update_node(node_id, status="active", tlp="TLP:GREEN")
    node = store.get_node(node_id)
    assert node["status"] == "active"
    assert node["tlp"] == "TLP:GREEN"


def test_delete_node(store) -> None:  # type: ignore[no-untyped-def]
    node_id = store.create_node("loss", "Loss A")
    store.delete_node(node_id)
    assert store.get_node(node_id) is None


def test_add_and_list_edges(store) -> None:  # type: ignore[no-untyped-def]
    haz_id = store.create_node("hazard", "Haz A")
    loss_id = store.create_node("loss", "Loss A")
    edge_id = store.add_edge(haz_id, loss_id, "leads-to")
    assert edge_id.startswith("EDG@")
    edges = store.list_edges(source_id=haz_id)
    assert len(edges) == 1
    assert edges[0]["conn_type"] == "leads-to"


def test_stats(store) -> None:  # type: ignore[no-untyped-def]
    store.create_node("loss", "L1")
    store.create_node("loss", "L2")
    haz_id = store.create_node("hazard", "H1")
    store.get_node(store.create_node("loss", "L3"))
    store.add_edge(haz_id, store.create_node("loss", "L4"), "leads-to")
    s = store.stats()
    assert s["node_count"] >= 4
    assert "loss" in s["by_type"]
    assert "hazard" in s["by_type"]


def test_arch_ref(store) -> None:  # type: ignore[no-untyped-def]
    node_id = store.create_node("hazard", "Haz A")
    store.register_arch_ref(node_id, "CSN@123.test.component", "binds-to")
    refs = store.list_arch_refs(assurance_node_id=node_id)
    assert len(refs) == 1
    assert refs[0]["arch_artifact_id"] == "CSN@123.test.component"


def test_operations_fail_when_locked(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415

    db_path = tmp_path / "locked.db"
    s = SQLCipherAssuranceStore(db_path)
    with pytest.raises(RuntimeError, match="locked"):
        s.list_nodes()
