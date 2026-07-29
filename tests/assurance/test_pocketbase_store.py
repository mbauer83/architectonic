"""Tests for the PocketBase assurance store adapter (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_client(items: list | None = None, total_items: int = 0):
    """Return a mock httpx.Client with sensible defaults."""
    client = MagicMock()
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.json.return_value = {"items": items or [], "totalItems": total_items}
    list_resp.raise_for_status = MagicMock()

    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {"id": "pb_abc123"}
    create_resp.raise_for_status = MagicMock()

    delete_resp = MagicMock()
    delete_resp.status_code = 204
    delete_resp.raise_for_status = MagicMock()

    client.get.return_value = list_resp
    client.post.return_value = create_resp
    client.patch.return_value = create_resp
    client.delete.return_value = delete_resp
    return client


def _make_store():
    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore  # noqa: PLC0415

    return PocketBaseAssuranceStore("http://localhost:8090", "admin@test.com", "secret")


def test_store_starts_locked() -> None:
    store = _make_store()
    assert not store.is_unlocked()


def test_operations_fail_when_locked() -> None:
    import pytest  # noqa: PLC0415

    store = _make_store()
    with pytest.raises(RuntimeError, match="locked"):
        store.list_nodes()


@patch("httpx.post")
@patch("httpx.Client")
def test_unlock_authenticates(mock_client_cls, mock_post) -> None:
    auth_resp = MagicMock()
    auth_resp.status_code = 200
    auth_resp.json.return_value = {"token": "test_token"}
    auth_resp.raise_for_status = MagicMock()
    mock_post.return_value = auth_resp
    mock_client_cls.return_value = MagicMock()

    store = _make_store()
    store.unlock()

    assert store.is_unlocked()
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "auth-with-password" in call_kwargs.args[0]


@patch("httpx.post")
@patch("httpx.Client")
def test_lock_clears_client(mock_client_cls, mock_post) -> None:
    auth_resp = MagicMock()
    auth_resp.status_code = 200
    auth_resp.json.return_value = {"token": "tok"}
    auth_resp.raise_for_status = MagicMock()
    mock_post.return_value = auth_resp
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance

    store = _make_store()
    store.unlock()
    store.lock()

    assert not store.is_unlocked()
    mock_instance.close.assert_called_once()


def test_create_node_returns_prefixed_id() -> None:
    store = _make_store()
    store._client = _mock_client()

    node_id = store.create_node("loss", "Loss of Control", concern_class="safety")

    assert node_id.startswith("LSS@")
    store._client.post.assert_called_once()


def test_get_node_returns_none_when_missing() -> None:
    store = _make_store()
    store._client = _mock_client(items=[])

    result = store.get_node("LSS@missing")

    assert result is None


def test_get_node_returns_first_item() -> None:
    fake_node = {"id": "pb1", "node_id": "LSS@1.test.abc123", "name": "Loss A"}
    store = _make_store()
    store._client = _mock_client(items=[fake_node])

    result = store.get_node("LSS@1.test.abc123")

    assert result is not None
    assert result["name"] == "Loss A"


def test_list_nodes_returns_items() -> None:
    items = [
        {"id": "pb1", "node_id": "LSS@1.x.y", "node_type": "loss"},
        {"id": "pb2", "node_id": "HAZ@1.x.y", "node_type": "hazard"},
    ]
    store = _make_store()
    store._client = _mock_client(items=items)

    nodes = store.list_nodes()

    assert len(nodes) == 2


def test_add_edge_returns_prefixed_id() -> None:
    store = _make_store()
    store._client = _mock_client()

    edge_id = store.add_edge("LSS@1", "HAZ@1", "leads-to")

    assert edge_id.startswith("EDG@")
    store._client.post.assert_called_once()


def test_remove_edge_calls_delete() -> None:
    fake_edge = {"id": "pb_e1", "edge_id": "EDG@abc"}
    store = _make_store()
    store._client = _mock_client(items=[fake_edge])

    store.remove_edge("EDG@abc")

    store._client.delete.assert_called_once()


def test_stats_returns_counts() -> None:
    count_resp = MagicMock()
    count_resp.status_code = 200
    count_resp.json.return_value = {"totalItems": 5}
    count_resp.raise_for_status = MagicMock()

    store = _make_store()
    store._client = MagicMock()
    store._client.get.return_value = count_resp

    stats = store.stats()

    assert stats["node_count"] == 5
    assert stats["edge_count"] == 5


def test_register_arch_ref_skips_duplicate() -> None:
    existing_ref = {"id": "pb_r1", "assurance_node_id": "LSS@1", "arch_artifact_id": "CSN@2", "ref_type": "binds-to"}
    store = _make_store()
    store._client = _mock_client(items=[existing_ref])

    store.register_arch_ref("LSS@1", "CSN@2", "binds-to")

    store._client.post.assert_not_called()


def test_register_arch_ref_posts_when_new() -> None:
    store = _make_store()
    store._client = _mock_client(items=[])

    store.register_arch_ref("LSS@1", "CSN@2", "binds-to")

    store._client.post.assert_called_once()
