"""The MCP structured-output normalizer contract.

`install_call_tool_normalizer` replaces the server's `tools/call` handler, so it owns the whole
answer: the readable content a model reads, and the structured content the tool's output schema
describes. What is asserted here is that the two say the same thing and that neither is lost —
a structured tool keeps its `structuredContent`, an unstructured one gains none, and both answer in
YAML rather than in a JSON blob.

Two test groups:
- TestStructuredOutputNormalizerContract: a synthetic server with one structured-output and one
  plain-dict tool.
- TestProductionReadServerStructuredOutputTools: the real `mcp_read` server, so the registration and
  the shape are checked against what actually ships.
"""

from __future__ import annotations

import asyncio
from typing import Any

import yaml
from mcp.server.context import ServerRequestContext
from mcp.types import CallToolRequestParams, TextContent

from src.infrastructure.mcp.artifact_mcp.name_normalization import install_call_tool_normalizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_structured_mcp():
    from mcp.server.mcpserver import MCPServer

    m = MCPServer(name="test-structured-output")

    @m.tool(name="structured_tool", structured_output=True)
    def structured_tool() -> dict[str, object]:
        return {"status": "ok", "count": 42}

    @m.tool(name="plain_dict_tool")
    def plain_dict_tool() -> dict:  # bare dict: MCPServer cannot serialize, stays unstructured
        return {"status": "plain"}

    install_call_tool_normalizer(m)
    return m


def _invoke(server, tool_name: str, arguments: dict[str, Any] | None = None):
    """Call the server's registered `tools/call` handler the way the runner would.

    `mcp` 2.x hands a handler `(context, params)` and takes a `CallToolResult` back, where 1.x passed
    a whole request object and returned a wrapper to unwrap. The context is built here rather than
    stubbed away, because the normalizer passes it on to the tool.
    """
    entry = server._lowlevel_server.get_request_handler("tools/call")
    params = CallToolRequestParams(name=tool_name, arguments=arguments or {})
    context = ServerRequestContext(
        session=None, lifespan_context=None, protocol_version=None,
        method="tools/call", params=params, request_id=1,
    )
    return asyncio.run(entry.handler(context, params))


# ---------------------------------------------------------------------------
# Unit tests — synthetic MCPServer
# ---------------------------------------------------------------------------


class TestStructuredOutputNormalizerContract:
    def test_structured_output_tool_populates_structured_content(self):
        result = _invoke(_build_structured_mcp(), "structured_tool")
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["status"] == "ok"

    def test_structured_output_tool_text_content_is_yaml(self):
        result = _invoke(_build_structured_mcp(), "structured_tool")
        assert not result.is_error
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert text_items, "expected at least one TextContent"
        parsed = yaml.safe_load(text_items[0].text)
        assert parsed == {"status": "ok", "count": 42}

    def test_structured_content_matches_text_content(self):
        """YAML text and structuredContent must represent the same data."""
        result = _invoke(_build_structured_mcp(), "structured_tool")
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert yaml.safe_load(text) == result.structured_content

    def test_plain_dict_tool_has_no_structured_content(self):
        """Non-structured tools must NOT populate structuredContent."""
        result = _invoke(_build_structured_mcp(), "plain_dict_tool")
        assert not result.is_error
        assert result.structured_content is None

    def test_plain_dict_result_is_yaml_text(self):
        result = _invoke(_build_structured_mcp(), "plain_dict_tool")
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert yaml.safe_load(text) == {"status": "plain"}

    def test_structured_content_is_not_json_string(self):
        """TextContent must be YAML, not a JSON blob (regression: pre-fix behaviour)."""
        result = _invoke(_build_structured_mcp(), "structured_tool")
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert not text.strip().startswith("{"), "TextContent looks like raw JSON, not YAML"


# ---------------------------------------------------------------------------
# Integration tests — production mcp_read server
# ---------------------------------------------------------------------------


class TestProductionReadServerStructuredOutputTools:
    def test_call_tool_request_handler_is_installed(self):
        """The custom normalizer replaces the default CallToolRequest handler."""
        from src.infrastructure.mcp.mcp_artifact_server import mcp_read

        entry = mcp_read._lowlevel_server.get_request_handler("tools/call")
        assert entry is not None
        assert entry.handler.__name__ == "_call_tool_handler"

    def test_expected_structured_output_tools_are_registered(self):
        from src.infrastructure.mcp.mcp_artifact_server import mcp_read

        tools = {t.name: t for t in mcp_read._tool_manager.list_tools()}
        structured = {name for name, t in tools.items() if t.fn_metadata.output_schema is not None}
        expected = {
            "artifact_query_stats",
            "artifact_query_search_artifacts",
            "artifact_query_list_artifacts",
            "artifact_query_read_artifact",
            "artifact_query_find_connections_for",
            "artifact_query_find_neighbors",
            "artifact_verify",
        }
        missing = expected - structured
        assert not missing, f"Structured-output tools not registered on mcp_read: {missing}"

    def test_artifact_query_stats_returns_structured_content(self, tmp_path):
        """End-to-end: artifact_query_stats populates structuredContent through the normalizer."""
        from src.infrastructure.mcp.mcp_artifact_server import mcp_read

        repo_root = tmp_path / "repo"
        (repo_root / "model").mkdir(parents=True)

        result = _invoke(
            mcp_read,
            "artifact_query_stats",
            {"repo_root": str(repo_root), "repo_scope": "engagement"},
        )
        assert not result.is_error, f"tool call failed: {result}"
        assert result.structured_content is not None, (
            "artifact_query_stats must populate structuredContent; "
            "if None the normalizer is not handling output_schema tools correctly"
        )

    def test_artifact_query_stats_yaml_matches_structured_content(self, tmp_path):
        from src.infrastructure.mcp.mcp_artifact_server import mcp_read

        repo_root = tmp_path / "repo"
        (repo_root / "model").mkdir(parents=True)

        result = _invoke(
            mcp_read,
            "artifact_query_stats",
            {"repo_root": str(repo_root), "repo_scope": "engagement"},
        )
        assert not result.is_error
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert yaml.safe_load(text) == result.structured_content
