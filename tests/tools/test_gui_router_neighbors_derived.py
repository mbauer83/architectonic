"""REST derived-neighbor traversal matches the MCP graph result."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.connections import router
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-R" / "architecture-repository"
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


def test_derived_neighbors_match_mcp(repo: Path) -> None:
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    component = _entity(repo, "application-component", "Component")
    function = _entity(repo, "function", "Function")
    service = _entity(repo, "service", "Service")
    _connection(repo, component, function, "archimate-assignment")
    _connection(repo, function, service, "archimate-realization")
    mcp_result = mcp.mcp_read._tool_manager._tools["artifact_query_find_neighbors"].fn(
        entity_id=component, traversal="derived", max_hops=2, repo_root=str(repo), repo_scope="engagement"
    )

    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    app = FastAPI()
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: build_runtime_catalogs(get_module_registry())
    app.include_router(router)
    rest_result = TestClient(app).get(f"/api/neighbors?entity_id={component}&traversal=derived&max_hops=2").json()

    assert rest_result["neighbors"] == mcp_result["neighbors"]["derived"]
