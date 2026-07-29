"""Every assurance-store connection enforces referential integrity, not just the first one.

`PRAGMA foreign_keys` is a per-connection setting that defaults to off, and it was declared
only inside the schema script — which runs once, on the connection that bootstraps the
store. Any other thread's connection therefore had foreign keys disabled, so deleting a node
through it removed the node and left its edges behind. Dangling edges are invisible to every
navigation surface and surface only as hard verifier findings, so the damage accumulated
silently in a live store.

The store is served from a thread pool (sync REST handlers and tool execution), which is why
the second and later connections are the normal case rather than an edge case.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLCipherAssuranceStore:
    from src.infrastructure.assurance import _credential_store as creds

    monkeypatch.setattr(creds, "get", lambda _account: "0" * 64)
    opened = SQLCipherAssuranceStore(tmp_path / "store.db")
    opened.unlock()
    return opened


def _foreign_keys_enabled(connection: object) -> bool:
    row = connection.execute("PRAGMA foreign_keys").fetchone()  # type: ignore[attr-defined]
    return bool(next(iter(row.values())) if isinstance(row, dict) else row[0])


def test_the_bootstrap_connection_enforces_foreign_keys(store: SQLCipherAssuranceStore) -> None:
    assert _foreign_keys_enabled(store.unlocked_connection())


def test_a_connection_opened_on_another_thread_enforces_foreign_keys(
    store: SQLCipherAssuranceStore,
) -> None:
    observed: list[bool] = []

    def check() -> None:
        observed.append(_foreign_keys_enabled(store.unlocked_connection()))

    worker = threading.Thread(target=check)
    worker.start()
    worker.join()

    assert observed == [True]


def test_deleting_a_node_from_another_thread_removes_its_edges(
    store: SQLCipherAssuranceStore,
) -> None:
    """The regression: a delete served on a pool thread used to leave the edges behind."""
    hazard_id = store.create_node("hazard", "Brakes are not applied in time")
    loss_id = store.create_node("loss", "Collision with the vehicle ahead")
    store.add_edge(hazard_id, loss_id, "leads-to")

    def delete() -> None:
        store.delete_node(hazard_id)

    worker = threading.Thread(target=delete)
    worker.start()
    worker.join()

    assert store.get_node(hazard_id) is None
    assert store.list_edges() == []
