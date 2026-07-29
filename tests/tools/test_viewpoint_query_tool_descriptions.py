"""Tool-description/schema tests for MCP read tool ``artifact_query_viewpoint`` (WU-E7a).

Covers: registration, parameter presence, description content, and the locked D15 boundary
— no presentation/styling/column parameter exists on this tool at all.
"""

from __future__ import annotations


def _get_read_tools() -> dict[str, object]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_read  # noqa: PLC0415

    return {t.name: t for t in mcp_read._tool_manager.list_tools()}  # type: ignore[attr-defined]


def _param_names(tool) -> set[str]:
    props = tool.parameters.get("properties", {})
    return set(props.keys())


class TestToolRegistration:
    def test_registered_on_read_server(self) -> None:
        tools = _get_read_tools()
        assert "artifact_query_viewpoint" in tools

    def test_not_registered_on_write_server(self) -> None:
        from src.infrastructure.mcp.mcp_artifact_server import mcp_write

        names = {t.name for t in mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]
        assert "artifact_query_viewpoint" not in names


class TestParameters:
    def test_expected_parameters_present(self) -> None:
        tool = _get_read_tools()["artifact_query_viewpoint"]
        params = _param_names(tool)
        assert {"action", "slug", "query", "limit", "parameters", "repo_root", "repo_scope"} <= params

    def test_no_presentation_styling_or_column_parameters(self) -> None:
        """Locked D15 boundary: presentation is authored only, never an execution parameter."""
        tool = _get_read_tools()["artifact_query_viewpoint"]
        params = _param_names(tool)
        forbidden = {"presentation", "styling", "styling_rules", "columns", "representation", "row_by", "column_by"}
        assert not (params & forbidden)


class TestDescription:
    def test_mentions_both_actions(self) -> None:
        desc = _get_read_tools()["artifact_query_viewpoint"].description
        assert "list" in desc
        assert "execute" in desc

    def test_points_to_help_topic_for_grammar(self) -> None:
        desc = _get_read_tools()["artifact_query_viewpoint"].description
        assert "artifact_help" in desc
