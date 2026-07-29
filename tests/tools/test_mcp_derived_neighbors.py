"""MCP derived-neighbor traversal uses the shared relationship engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-D" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connection(repo: Path, source: str, target: str, connection_type: str) -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=connection_type, dry_run=False, repo_root=str(repo)
    )
    assert result["wrote"], result


def _tool():
    return mcp.mcp_read._tool_manager._tools["artifact_query_find_neighbors"].fn


def test_returns_derived_neighbor_witness_metadata(repo: Path) -> None:
    component = _entity(repo, "application-component", "Component")
    function = _entity(repo, "function", "Function")
    service = _entity(repo, "service", "Service")
    _connection(repo, component, function, "archimate-assignment")
    _connection(repo, function, service, "archimate-realization")

    result = _tool()(entity_id=component, traversal="derived", max_hops=2, repo_root=str(repo), repo_scope="engagement")

    derived = result["neighbors"]["derived"]
    assert len(derived) == 1
    assert derived[0]["entity_id"] == service
    assert derived[0]["type"] == "archimate-realization"
    assert derived[0]["certainty"] == "certain"
    assert derived[0]["hops"] == 2
    assert len(derived[0]["via_connection_ids"]) == 2
    assert derived[0]["path"]


def test_limit_error_has_no_neighbor_payload(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    component = _entity(repo, "application-component", "Component")
    function = _entity(repo, "function", "Function")
    service = _entity(repo, "service", "Service")
    _connection(repo, component, function, "archimate-assignment")
    _connection(repo, function, service, "archimate-realization")
    monkeypatch.setattr(
        "src.infrastructure.mcp.artifact_mcp.query_graph_tools.viewpoints_derivation_max_relationships", lambda: 0
    )

    result = _tool()(entity_id=component, traversal="derived", max_hops=2, repo_root=str(repo), repo_scope="engagement")

    assert result["error"]["code"] == "derivation-limit"
    assert "neighbors" not in result
