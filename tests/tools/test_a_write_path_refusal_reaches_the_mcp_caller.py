"""A write-path refusal reaches an MCP caller as its sentence, not as a crash (B82).

The write path refuses with ``ValueError`` whose message names what was wrong and what to do instead.
`mcp` 2.x reports anything other than ``ToolError`` as "Error executing tool <name>" and drops the
message, so a caller of ``artifact_edit_diagram`` refused for a model-backed diagram learned only that
the tool had failed. The MCP call handler translates the refusal at its boundary; a genuine crash
still reads as one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolRequestParams, TextContent

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.name_normalization import install_call_tool_normalizer


def _invoke(server: MCPServer, tool_name: str, arguments: dict[str, Any] | None = None):
    entry = server._lowlevel_server.get_request_handler("tools/call")
    params = CallToolRequestParams(name=tool_name, arguments=arguments or {})
    context = ServerRequestContext(
        session=None, lifespan_context=None, protocol_version=None,
        method="tools/call", params=params, request_id=1,
    )
    return asyncio.run(entry.handler(context, params))


def _text(result: Any) -> str:
    return next(c.text for c in result.content if isinstance(c, TextContent))


def _server() -> MCPServer:
    server = MCPServer(name="test-refusals")

    @server.tool(name="refuses")
    def refuses() -> dict:
        raise ValueError("Pass diagram_entities to change what it draws.")

    @server.tool(name="crashes")
    def crashes() -> dict:
        raise KeyError("internal detail")

    install_call_tool_normalizer(server)
    return server


def test_a_value_error_is_answered_with_its_sentence() -> None:
    result = _invoke(_server(), "refuses")

    assert result.is_error
    assert _text(result) == "Pass diagram_entities to change what it draws."


def test_a_crash_still_reads_as_a_crash() -> None:
    result = _invoke(_server(), "crashes")

    assert result.is_error
    assert "internal detail" not in _text(result)
    assert "Error executing tool crashes" in _text(result)


def test_an_authorization_denial_names_its_reason(tmp_path: Path) -> None:
    """End to end through the shipped write server: a write outside the served root is denied by policy."""
    repo = tmp_path / "engagements" / "ENG-REF" / "architecture-repository"
    (repo / "model").mkdir(parents=True)

    result = _invoke(mcp.mcp_write, "artifact_create_entity", {
        "artifact_type": "goal", "name": "A goal", "summary": "Summary", "repo_root": str(repo), "dry_run": False,
    })

    assert result.is_error
    assert "active engagement root" in _text(result), _text(result)
