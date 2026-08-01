"""Ordering an assurance node listing must not change what a reader is allowed to see.

Ordering happens in the store and the exposure filter runs over the result. Filtering is
order-preserving, so the surviving rows are the same set in a different order — but that is
exactly the kind of property that breaks silently if someone later sorts *after* filtering and
pages the result, or derives a count from the pre-filter list. These tests pin it: for every
supported sort field and direction, the same nodes are exposed, the same withheld flag is
reported, and no above-ceiling name appears anywhere in the payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from src.application.assurance_node_sorting import NODE_SORT_COLUMNS, sorted_node_dicts
from tests.support.api_app import build_api_app
from tests.support.assurance_records import node_record

pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

_ASSURANCE_CTX_PATH = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"

_SECRET_NAME = "SECRET HAZARD NAME"

_NODES: list[dict[str, Any]] = [
    node_record(node_id="LSS@1", node_type="loss", name="Alpha Loss", tlp="TLP:WHITE",
                created_at="2026-01-01T00:00:00Z", updated_at="2026-07-20T00:00:00Z"),
    node_record(node_id="HAZ@2", node_type="hazard", name=_SECRET_NAME, tlp="TLP:RED",
                created_at="2026-01-02T00:00:00Z", updated_at="2026-07-22T00:00:00Z"),
    node_record(node_id="CON@3", node_type="constraint", name="Zulu Constraint", tlp="TLP:AMBER",
                created_at="2026-01-03T00:00:00Z", updated_at="2026-07-01T00:00:00Z"),
]


class _SortingStore:
    """A store that honours sort/order the way every real adapter must."""

    def __init__(self, nodes: list[dict[str, Any]]) -> None:
        self._nodes = nodes

    def is_unlocked(self) -> bool:
        return True

    def list_nodes(self, *, node_type=None, status=None, concern_class=None, tlp=None,
                   analysis_id=None, sort=None, order=None) -> list[dict[str, Any]]:
        return sorted_node_dicts(self._nodes, sort, order)

    def list_edges(self, *, source_id=None, target_id=None, conn_type=None) -> list[dict[str, Any]]:
        """These tests are about ordering and exposure, not connectivity — but the endpoint
        reports each node's degree, so the store has to answer for edges as every real adapter
        does. An empty set keeps the ordering assertions about ordering."""
        return []


class _Context:
    def __init__(self, store: _SortingStore, ceiling: str) -> None:
        self._store = store
        self.max_classification = ceiling

    @property
    def store(self) -> _SortingStore:
        return self._store

    def is_available(self) -> bool:
        return self._store.is_unlocked()


def _client(ceiling: str) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    # `build_api_app`, not a bare `FastAPI()`: without the error contracts installed a raised
    # `ApiError` becomes a 500 with an empty body, and these tests then compare two empty bodies
    # while claiming an above-ceiling read is indistinguishable from an absent one.
    client = TestClient(build_api_app(router), raise_server_exceptions=False)
    patcher = patch(_ASSURANCE_CTX_PATH, return_value=_Context(_SortingStore(_NODES), ceiling))
    patcher.start()
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


@pytest.fixture()
def amber_reader() -> Iterator[TestClient]:
    """A reader cleared to TLP:AMBER — the TLP:RED hazard must stay withheld."""
    client = _client("TLP:AMBER")
    yield client
    client._patcher.stop()  # type: ignore[attr-defined]


@pytest.fixture()
def red_reader() -> Iterator[TestClient]:
    client = _client("TLP:RED")
    yield client
    client._patcher.stop()  # type: ignore[attr-defined]


def _all_sorts() -> list[tuple[str, str]]:
    return [(field, order) for field in sorted(NODE_SORT_COLUMNS) for order in ("asc", "desc")]


def test_default_ordering_is_most_recently_updated_first(red_reader: TestClient) -> None:
    body = red_reader.get("/api/assurance/nodes").json()
    assert [n["node_id"] for n in body["nodes"]] == ["HAZ@2", "LSS@1", "CON@3"]


def test_requested_ordering_is_applied(red_reader: TestClient) -> None:
    body = red_reader.get("/api/assurance/nodes", params={"sort": "name", "order": "asc"}).json()
    assert [n["node_id"] for n in body["nodes"]] == ["LSS@1", "HAZ@2", "CON@3"]


def test_exposed_set_is_identical_under_every_ordering(amber_reader: TestClient) -> None:
    baseline = {n["node_id"] for n in amber_reader.get("/api/assurance/nodes").json()["nodes"]}
    assert baseline == {"LSS@1", "CON@3"}

    for field, order in _all_sorts():
        body = amber_reader.get("/api/assurance/nodes", params={"sort": field, "order": order}).json()
        assert {n["node_id"] for n in body["nodes"]} == baseline, f"sort={field} order={order}"


def test_withheld_signal_is_unchanged_by_ordering(amber_reader: TestClient) -> None:
    for field, order in _all_sorts():
        body = amber_reader.get("/api/assurance/nodes", params={"sort": field, "order": order}).json()
        assert body["visibility_limited"] is True
        assert body["count"] == 2, "count must describe the exposed rows, never the withheld ones"


def test_no_ordering_leaks_an_above_ceiling_name(amber_reader: TestClient) -> None:
    for field, order in _all_sorts():
        response = amber_reader.get("/api/assurance/nodes", params={"sort": field, "order": order})
        assert _SECRET_NAME not in response.text
        assert "HAZ@2" not in response.text


def test_an_unknown_sort_field_neither_errors_nor_widens_exposure(amber_reader: TestClient) -> None:
    response = amber_reader.get("/api/assurance/nodes", params={"sort": "tlp", "order": "desc"})
    assert response.status_code == 200
    body = response.json()
    assert {n["node_id"] for n in body["nodes"]} == {"LSS@1", "CON@3"}
    assert _SECRET_NAME not in response.text
