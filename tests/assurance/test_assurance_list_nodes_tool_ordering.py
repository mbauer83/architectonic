"""The `assurance_list_nodes` MCP tool asks the store for an order, and exposure still decides.

An agent listing nodes needs "what changed most recently" as much as a human does, and the tool
must get there the same way the HTTP surface does: the store orders, then the exposure policy
filters. This drives the registered tool function itself, so the parameters it actually accepts
are what is under test.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance_node_sorting import sorted_node_dicts

mcp_server = pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

_SECRET_NAME = "SECRET HAZARD NAME"

_NODES: list[dict[str, Any]] = [
    {"node_id": "LSS@1", "node_type": "loss", "name": "Alpha Loss", "tlp": "TLP:WHITE",
     "status": "draft", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-07-20T00:00:00Z"},
    {"node_id": "HAZ@2", "node_type": "hazard", "name": _SECRET_NAME, "tlp": "TLP:RED",
     "status": "draft", "created_at": "2026-01-02T00:00:00Z", "updated_at": "2026-07-22T00:00:00Z"},
    {"node_id": "CON@3", "node_type": "constraint", "name": "Zulu Constraint", "tlp": "TLP:AMBER",
     "status": "draft", "created_at": "2026-01-03T00:00:00Z", "updated_at": "2026-07-01T00:00:00Z"},
]


class _RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []

    def is_unlocked(self) -> bool:
        return True

    def list_nodes(self, *, node_type=None, status=None, concern_class=None, tlp=None,
                   analysis_id=None, sort=None, order=None) -> list[dict[str, Any]]:
        self.calls.append((sort, order))
        return sorted_node_dicts(_NODES, sort, order)


class _Context:
    def __init__(self, store: _RecordingStore, ceiling: str) -> None:
        self._store = store
        self.max_classification = ceiling

    @property
    def store(self) -> _RecordingStore:
        return self._store

    def is_available(self) -> bool:
        return True

    def locked_response(self) -> dict[str, object]:
        return {"error": "assurance_store_locked"}


def _list_nodes_tool(ceiling: str, monkeypatch) -> tuple[Any, _RecordingStore]:
    """Register the read tools against a context we control, then hand back the tool function.

    The registration closure captures the context, so the fake has to be in place first.
    """
    from src.infrastructure.mcp.assurance_mcp import context as ctx_module
    from src.infrastructure.mcp.assurance_mcp import read_tools

    store = _RecordingStore()
    monkeypatch.setattr(ctx_module, "_CTX", _Context(store, ceiling))
    server = mcp_server.FastMCP("assurance-read-under-test")
    read_tools.register_read_tools(server)
    return server._tool_manager._tools["assurance_list_nodes"].fn, store  # noqa: SLF001


def test_defaults_to_most_recently_updated_first(monkeypatch) -> None:
    list_nodes, store = _list_nodes_tool("TLP:RED", monkeypatch)

    result = list_nodes()

    assert store.calls == [("updated_at", "desc")]
    assert [node["node_id"] for node in result["nodes"]] == ["HAZ@2", "LSS@1", "CON@3"]


def test_a_requested_order_reaches_the_store(monkeypatch) -> None:
    list_nodes, store = _list_nodes_tool("TLP:RED", monkeypatch)

    result = list_nodes(sort="name", order="asc")

    assert store.calls == [("name", "asc")]
    assert [node["node_id"] for node in result["nodes"]] == ["LSS@1", "HAZ@2", "CON@3"]


def test_ordering_never_widens_what_an_agent_may_see(monkeypatch) -> None:
    list_nodes, _store = _list_nodes_tool("TLP:AMBER", monkeypatch)

    for sort in ("updated_at", "created_at", "name", "node_type"):
        for order in ("asc", "desc"):
            result = list_nodes(sort=sort, order=order)
            assert {node["node_id"] for node in result["nodes"]} == {"LSS@1", "CON@3"}
            assert result["count"] == 2
            assert result["withheld"] == 1
            assert _SECRET_NAME not in str(result)
