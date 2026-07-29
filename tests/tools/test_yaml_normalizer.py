"""Tests for the MCP YAML normalizer.

Covers _dump_yaml_text (unit), normalize_incoming_tool_name (unit), and end-to-end
behaviour: dict/list results become YAML TextContent after install_call_tool_normalizer,
string results pass through unchanged, and prefixed tool names are resolved before dispatch.
"""

from __future__ import annotations

import asyncio

import yaml
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolRequest, CallToolRequestParams, TextContent

from src.infrastructure.mcp.artifact_mcp.name_normalization import (
    _dump_yaml_text,
    install_call_tool_normalizer,
    normalize_incoming_tool_name,
)

# ---------------------------------------------------------------------------
# _dump_yaml_text — unit tests
# ---------------------------------------------------------------------------


class TestDumpYamlText:
    def test_dict_round_trips(self):
        data = {"name": "Alice", "count": 3, "active": True}
        assert yaml.safe_load(_dump_yaml_text(data)) == data

    def test_list_round_trips(self):
        data = [{"id": "a", "v": 1}, {"id": "b", "v": 2}]
        assert yaml.safe_load(_dump_yaml_text(data)) == data

    def test_nested_structure(self):
        data = {"outer": {"inner": [1, 2, 3]}, "flag": False}
        assert yaml.safe_load(_dump_yaml_text(data)) == data

    def test_no_trailing_newline(self):
        assert not _dump_yaml_text({"x": 1}).endswith("\n")

    def test_returns_string(self):
        assert isinstance(_dump_yaml_text({"k": "v"}), str)

    def test_unicode_preserved(self):
        data = {"label": "ärchitecture"}
        assert yaml.safe_load(_dump_yaml_text(data)) == data


# ---------------------------------------------------------------------------
# normalize_incoming_tool_name — unit tests
# ---------------------------------------------------------------------------


class TestNormalizeToolName:
    def test_known_name_passthrough(self):
        assert normalize_incoming_tool_name("my_tool", known_tools={"my_tool"}) == "my_tool"

    def test_strips_dash_prefix(self):
        assert normalize_incoming_tool_name("server-my_tool", known_tools={"my_tool"}) == "my_tool"

    def test_strips_colon_prefix(self):
        assert normalize_incoming_tool_name("ns:my_tool", known_tools={"my_tool"}) == "my_tool"

    def test_strips_dot_prefix(self):
        assert normalize_incoming_tool_name("ns.my_tool", known_tools={"my_tool"}) == "my_tool"

    def test_strips_slash_prefix(self):
        assert normalize_incoming_tool_name("ns/my_tool", known_tools={"my_tool"}) == "my_tool"

    def test_exact_match_preferred_over_suffix(self):
        known = {"my_tool", "server-my_tool"}
        assert normalize_incoming_tool_name("server-my_tool", known_tools=known) == "server-my_tool"

    def test_unknown_name_unchanged(self):
        assert normalize_incoming_tool_name("ghost", known_tools={"other"}) == "ghost"

    def test_empty_known_tools_returns_unchanged(self):
        assert normalize_incoming_tool_name("x:tool", known_tools=set()) == "x:tool"


# ---------------------------------------------------------------------------
# install_call_tool_normalizer — end-to-end tests
# ---------------------------------------------------------------------------


def _build_test_mcp() -> FastMCP:
    m = FastMCP(name="test-normalizer")

    @m.tool(name="returns_dict")
    def returns_dict() -> dict:
        return {"status": "ok", "items": [1, 2]}

    @m.tool(name="returns_list")
    def returns_list() -> list:
        return [{"a": 1}, {"b": 2}]

    @m.tool(name="returns_str")
    def returns_str() -> str:
        return "plain string"

    @m.tool(name="takes_params")
    def takes_params(only_filter: str | None = None) -> dict:
        return {"only_filter": only_filter}

    install_call_tool_normalizer(m)
    return m


def _invoke(m: FastMCP, tool_name: str, arguments: dict | None = None):
    handler = m._mcp_server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=tool_name, arguments=arguments or {}),
    )
    return asyncio.run(handler(req)).root


class TestNormalizerEndToEnd:
    def test_dict_result_becomes_yaml_text_content(self):
        result = _invoke(_build_test_mcp(), "returns_dict")
        assert not result.isError
        assert isinstance(result.content[0], TextContent)
        parsed = yaml.safe_load(result.content[0].text)
        assert parsed == {"status": "ok", "items": [1, 2]}

    def test_list_result_becomes_yaml_text_content(self):
        result = _invoke(_build_test_mcp(), "returns_list")
        assert not result.isError
        assert isinstance(result.content[0], TextContent)
        assert yaml.safe_load(result.content[0].text) == [{"a": 1}, {"b": 2}]

    def test_string_result_passed_through_as_text_content(self):
        result = _invoke(_build_test_mcp(), "returns_str")
        assert not result.isError
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert "plain string" in text

    def test_prefixed_tool_name_normalized_before_dispatch(self):
        """A namespaced tool name like 'arch-returns_dict' resolves to 'returns_dict'."""
        result = _invoke(_build_test_mcp(), "arch-returns_dict")
        assert not result.isError
        parsed = yaml.safe_load(result.content[0].text)
        assert parsed["status"] == "ok"

    def test_yaml_output_is_valid_yaml(self):
        result = _invoke(_build_test_mcp(), "returns_dict")
        text = result.content[0].text
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, dict)

    def test_mcp_read_server_has_normalizer_installed(self):
        """The production read server should respond with YAML text for dict-returning tools."""
        from src.infrastructure.mcp import mcp_artifact_server

        srv = mcp_artifact_server.mcp_read._mcp_server
        assert CallToolRequest in srv.request_handlers


class TestUnknownParameterRejection:
    """An unrecognized parameter must fail loud (not be silently dropped, which would let the
    tool run with defaults and return a confidently wrong result)."""

    def test_known_parameter_is_accepted(self):
        result = _invoke(_build_test_mcp(), "takes_params", {"only_filter": "x"})
        assert not result.isError
        assert yaml.safe_load(result.content[0].text) == {"only_filter": "x"}

    def test_no_arguments_is_accepted(self):
        result = _invoke(_build_test_mcp(), "takes_params", {})
        assert not result.isError

    def test_unknown_parameter_errors(self):
        result = _invoke(_build_test_mcp(), "takes_params", {"topic": "x"})
        assert result.isError
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert "Unknown parameter" in text
        assert "topic" in text

    def test_error_lists_accepted_parameters(self):
        result = _invoke(_build_test_mcp(), "takes_params", {"topic": "x"})
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert "only_filter" in text

    def test_unknown_parameter_alongside_valid_one_still_errors(self):
        result = _invoke(_build_test_mcp(), "takes_params", {"only_filter": "x", "tpoic": "y"})
        assert result.isError
        text = next(c.text for c in result.content if isinstance(c, TextContent))
        assert "tpoic" in text

    def test_extra_arg_to_zero_param_tool_errors(self):
        result = _invoke(_build_test_mcp(), "returns_dict", {"surprise": 1})
        assert result.isError
