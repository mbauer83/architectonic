"""`DELETE /api/assurance/nodes/{node_id}` refuses a node another analysis references, over HTTP.

The store-level rule is covered across all four backends in
``test_analysis_deletion_conformance.py``; this is the other half — that the refusal reaches a client
as the published contract rather than as a 500 or a silent 204.

`entity_in_use` was in the closed error vocabulary (`contracts/errors.py:43`) with a details DTO naming
the referencing analyses (`:102`) and a code→DTO mapping (`:170`), and nothing produced it. A published
code no code path can return is a contract lie in the same family as an undocumented body: a generated
client branches on it, and the branch is dead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_CTX_PATH = "src.infrastructure.rest.routers.assurance._write.get_assurance_context"


class _RealContext:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.archive = _Archive()
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        return bool(self.store.is_unlocked())

    def locked_response(self) -> dict[str, object]:
        return {"error": "assurance_store_locked"}


class _Archive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, operation: str, **_kwargs: object) -> dict[str, object]:
        self.ops.append(operation)
        return {"operation": operation}


@pytest.fixture()
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "nodes.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _RealContext(store)
    store.lock()


@pytest.fixture()
def client(ctx: Any):  # type: ignore[no-untyped-def]
    from src.infrastructure.rest.routers.assurance._write import write_router

    started = patch(_CTX_PATH, return_value=ctx)
    started.start()
    with TestClient(build_api_app(write_router), raise_server_exceptions=False) as test_client:
        yield test_client
    started.stop()


@pytest.fixture()
def borrowed(ctx: Any) -> tuple[str, str, str]:
    """A node authored by one analysis and referenced by another. Fixture content the test owns."""
    store = ctx.store
    author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
    borrower = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
    node = str(store.create_node("hazard", "Load path is unguarded", analysis_id=author))
    store.add_analysis_member(borrower, node)
    return author, borrower, node


def test_the_refusal_is_a_409_in_the_shared_envelope(client: TestClient, borrowed: Any) -> None:
    _author, _borrower, node = borrowed

    response = client.delete(f"/api/assurance/nodes/{node}")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "entity_in_use"


def test_the_details_name_the_analyses_holding_the_references(
    client: TestClient, borrowed: Any
) -> None:
    """The caller's next action is to remove those references; a code alone would send them looking."""
    _author, borrower, node = borrowed

    response = client.delete(f"/api/assurance/nodes/{node}")

    details = response.json()["detail"]["details"]
    assert details["node_id"] == node
    assert details["referencing_analysis_ids"] == [borrower]


def test_the_refusal_carries_no_store(client: TestClient, borrowed: Any) -> None:
    """Every response on this surface, success and error alike — the confidentiality contract does not
    have an exception for refusals, and a 409 body names analysis ids."""
    _author, _borrower, node = borrowed

    response = client.delete(f"/api/assurance/nodes/{node}")

    assert response.headers["Cache-Control"] == "no-store"


def test_nothing_is_deleted_by_a_refused_request(
    client: TestClient, ctx: Any, borrowed: Any
) -> None:
    """A refusal that had already deleted would be worse than the cascade: the caller is told to
    remove references to a node that is gone."""
    _author, borrower, node = borrowed

    client.delete(f"/api/assurance/nodes/{node}")

    assert ctx.store.get_node(node) is not None
    assert ctx.store.list_analysis_members(borrower) == [node]
    assert ctx.archive.ops == []


def test_an_unreferenced_node_still_deletes_with_204(client: TestClient, ctx: Any) -> None:
    """The rule is about references. If it refused everything the surface would look protected while
    being append-only."""
    author = str(ctx.store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
    node = str(ctx.store.create_node("hazard", "Nobody cites this", analysis_id=author))

    response = client.delete(f"/api/assurance/nodes/{node}")

    assert response.status_code == 204
    assert response.content == b""
    assert ctx.store.get_node(node) is None


def test_it_deletes_once_the_reference_is_removed(
    client: TestClient, ctx: Any, borrowed: Any
) -> None:
    """"Until references are explicitly removed" — the refusal is a state the caller can leave."""
    _author, borrower, node = borrowed
    ctx.store.remove_analysis_member(borrower, node)

    response = client.delete(f"/api/assurance/nodes/{node}")

    assert response.status_code == 204
    assert ctx.store.get_node(node) is None
