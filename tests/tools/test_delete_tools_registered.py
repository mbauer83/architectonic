"""artifact_delete_entity/artifact_delete_diagram/artifact_delete_document are registered
as MCP tools, not just plain Python functions.

Regression coverage: these three functions were defined in edit_tools.py/write/document.py
and imported into mcp_artifact_server.py, but `register_edit_tools`/`register` never passed
them to `mcp.tool(...)` — so no MCP/LLM caller could actually invoke them; only
`artifact_bulk_delete` (with a one-element items list) was reachable for a single delete.
Fixed by registering them alongside their siblings. This test would have failed before that
fix even though calling the plain functions directly (as other tests do) always worked.
"""

from __future__ import annotations


def _get_write_tools() -> dict[str, object]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_write  # noqa: PLC0415

    return {t.name: t for t in mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]


def test_delete_entity_is_registered() -> None:
    tools = _get_write_tools()
    assert "artifact_delete_entity" in tools, "artifact_delete_entity not registered as an MCP tool"
    assert "artifact_id" in tools["artifact_delete_entity"].parameters.get("properties", {})


def test_delete_diagram_is_registered() -> None:
    tools = _get_write_tools()
    assert "artifact_delete_diagram" in tools, "artifact_delete_diagram not registered as an MCP tool"
    assert "artifact_id" in tools["artifact_delete_diagram"].parameters.get("properties", {})


def test_delete_document_is_registered() -> None:
    tools = _get_write_tools()
    assert "artifact_delete_document" in tools, "artifact_delete_document not registered as an MCP tool"
    assert "artifact_id" in tools["artifact_delete_document"].parameters.get("properties", {})
