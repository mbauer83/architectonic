"""Tests for the private-git-backed assurance store adapter."""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def store(tmp_path):
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore  # noqa: PLC0415

    s = PrivateGitAssuranceStore(tmp_path / "assurance-repo")
    s.unlock()
    yield s
    s.lock()


def test_unlock_creates_directories(tmp_path) -> None:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore  # noqa: PLC0415

    repo = tmp_path / "repo"
    s = PrivateGitAssuranceStore(repo)
    s.unlock()

    assert (repo / "nodes").is_dir()
    assert (repo / "edges").is_dir()
    assert (repo / "refs").is_dir()


def test_lock_prevents_operations(tmp_path) -> None:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore  # noqa: PLC0415

    s = PrivateGitAssuranceStore(tmp_path / "repo")
    with pytest.raises(RuntimeError, match="locked"):
        s.list_nodes()


def test_create_and_get_node(store) -> None:
    node_id = store.create_node("loss", "System Failure", concern_class="safety")

    assert node_id.startswith("LSS@")
    node = store.get_node(node_id)
    assert node is not None
    assert node["node_type"] == "loss"
    assert node["name"] == "System Failure"
    assert node["concern_class"] == "safety"


def test_get_node_returns_none_when_missing(store) -> None:
    assert store.get_node("LSS@nonexistent") is None


def test_list_nodes_filter_by_type(store) -> None:
    store.create_node("loss", "Loss A")
    store.create_node("hazard", "Hazard B")

    losses = store.list_nodes(node_type="loss")
    hazards = store.list_nodes(node_type="hazard")

    assert all(n["node_type"] == "loss" for n in losses)
    assert all(n["node_type"] == "hazard" for n in hazards)


def test_update_node(store) -> None:
    node_id = store.create_node("loss", "Loss A")
    store.update_node(node_id, status="active", tlp="TLP:GREEN")

    node = store.get_node(node_id)
    assert node["status"] == "active"
    assert node["tlp"] == "TLP:GREEN"


def test_update_node_attributes(store) -> None:
    node_id = store.create_node("risk", "Risk A")
    store.update_node(node_id, attributes={"likelihood": "high", "impact": "critical"})

    node = store.get_node(node_id)
    attrs = json.loads(str(node["attributes_json"]))
    assert attrs["likelihood"] == "high"


def test_delete_node(store) -> None:
    node_id = store.create_node("loss", "Loss A")
    store.delete_node(node_id)

    assert store.get_node(node_id) is None


def test_add_and_list_edges(store) -> None:
    haz_id = store.create_node("hazard", "Haz A")
    loss_id = store.create_node("loss", "Loss A")
    edge_id = store.add_edge(haz_id, loss_id, "leads-to")

    assert edge_id.startswith("EDG@")
    edges = store.list_edges(source_id=haz_id)
    assert len(edges) == 1
    assert edges[0]["conn_type"] == "leads-to"


def test_remove_edge(store) -> None:
    haz_id = store.create_node("hazard", "H1")
    loss_id = store.create_node("loss", "L1")
    edge_id = store.add_edge(haz_id, loss_id, "leads-to")
    store.remove_edge(edge_id)

    assert store.list_edges(source_id=haz_id) == []


def test_arch_ref_round_trip(store) -> None:
    node_id = store.create_node("hazard", "Haz A")
    store.register_arch_ref(node_id, "CSN@123.test.abc", "binds-to")

    refs = store.list_arch_refs(assurance_node_id=node_id)
    assert len(refs) == 1
    assert refs[0]["arch_artifact_id"] == "CSN@123.test.abc"
    assert refs[0]["resolved_at"] is None


def test_arch_ref_mark_resolved(store) -> None:
    node_id = store.create_node("hazard", "Haz A")
    store.register_arch_ref(node_id, "ARC@1", "binds-to")
    store.mark_arch_ref_resolved(node_id, "ARC@1", "binds-to")

    refs = store.list_arch_refs(assurance_node_id=node_id)
    assert refs[0]["resolved_at"] is not None


def test_register_arch_ref_idempotent(store) -> None:
    node_id = store.create_node("hazard", "Haz A")
    store.register_arch_ref(node_id, "ARC@1", "binds-to")
    store.register_arch_ref(node_id, "ARC@1", "binds-to")

    refs = store.list_arch_refs(assurance_node_id=node_id)
    assert len(refs) == 1


def test_stats_counts_files(store) -> None:
    store.create_node("loss", "L1")
    store.create_node("loss", "L2")
    haz_id = store.create_node("hazard", "H1")
    loss_id = store.create_node("loss", "L3")
    store.add_edge(haz_id, loss_id, "leads-to")

    stats = store.stats()
    assert stats["node_count"] == 4
    assert stats["edge_count"] == 1
