"""GAR visibility on the MCP search surface.

The MCP composition root (`repo_cached`) injects the internal-type exclusion set, so
`artifact_query_search_artifacts` must never return GAR proxies while raw list/read
tools keep seeing them.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.mcp import mcp_artifact_server
from tests.support.search_visibility_fixtures import (
    GAR_ID,
    GAR_TYPE,
    QUERY,
    REQ_ID,
    build_engagement_repo,
)


def _tool(name: str):
    return mcp_artifact_server.mcp_read._tool_manager._tools[name].fn


class TestMcpSearchHidesGar:
    def test_gar_absent_real_entity_present(self, tmp_path: Path) -> None:
        root = build_engagement_repo(tmp_path)
        result = _tool("artifact_query_search_artifacts")(
            QUERY, repo_root=str(root), repo_scope="engagement", limit=20
        )
        ids = [str(h["artifact_id"]) for h in result["hits"]]
        assert REQ_ID in ids
        assert GAR_ID not in ids

    def test_explicit_gar_type_query_returns_zero_entity_hits(self, tmp_path: Path) -> None:
        root = build_engagement_repo(tmp_path)
        result = _tool("artifact_query_search_artifacts")(
            QUERY,
            repo_root=str(root),
            repo_scope="engagement",
            artifact_type=GAR_TYPE,
            include_record_types=["entities"],
        )
        assert result["hits"] == []


class TestMcpRawAccessKeepsGar:
    def test_list_artifacts_still_returns_gar(self, tmp_path: Path) -> None:
        root = build_engagement_repo(tmp_path)
        listed = _tool("artifact_query_list_artifacts")(
            repo_root=str(root),
            repo_scope="engagement",
            artifact_type=GAR_TYPE,
            include_record_types=["entities"],
            fields=["artifact_id"],
        )
        assert [row["artifact_id"] for row in listed] == [GAR_ID]

    def test_read_artifact_still_returns_gar(self, tmp_path: Path) -> None:
        root = build_engagement_repo(tmp_path)
        record = _tool("artifact_query_read_artifact")(
            GAR_ID, repo_root=str(root), repo_scope="engagement"
        )
        assert record["artifact_id"] == GAR_ID
