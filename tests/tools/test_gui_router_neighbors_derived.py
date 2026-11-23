"""REST derived-neighbor traversal matches the MCP graph result."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.connections.router import router
from tests.support.api_app import build_api_app


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

    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.rest.dependencies import runtime_catalogs_dependency

    component = _entity(repo, "application-component", "Component")
    function = _entity(repo, "function", "Function")
    service = _entity(repo, "service", "Service")
    _connection(repo, component, function, "archimate-assignment")
    _connection(repo, function, service, "archimate-realization")
    mcp_result = mcp.mcp_read._tool_manager._tools["artifact_query_find_neighbors"].fn(
        entity_id=component, traversal="derived", max_hops=2, repo_root=str(repo), repo_scope="engagement"
    )

    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    app = build_api_app(router)
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: build_runtime_catalogs(get_module_registry())
    rest_result = TestClient(app).get(
        f"/api/entities/{component}/neighbors?traversal=derived&max_hops=2"
    ).json()

    assert rest_result["neighbors"] == mcp_result["neighbors"]["derived"]


def _client():
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.rest.dependencies import runtime_catalogs_dependency

    app = build_api_app(router)
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: build_runtime_catalogs(get_module_registry())
    return TestClient(app)


def _chain(repo: Path) -> tuple[str, str, str]:
    component = _entity(repo, "application-component", "Component")
    function = _entity(repo, "function", "Function")
    service = _entity(repo, "service", "Service")
    _connection(repo, component, function, "archimate-assignment")
    _connection(repo, function, service, "archimate-realization")
    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    return component, function, service


def test_each_derived_neighbour_says_which_way_it_runs(repo: Path) -> None:
    """Read from either end, one derived relationship is outbound at its source and inbound at its target.

    The diagram reader splits what leads to an element from what it leads to; without the direction
    the derived rows could only be listed as one undirected heap.
    """
    component, _function, service = _chain(repo)
    client = _client()

    from_source = client.get(f"/api/entities/{component}/neighbors?traversal=derived&max_hops=2").json()
    from_target = client.get(f"/api/entities/{service}/neighbors?traversal=derived&max_hops=2").json()

    assert [(row["entity_id"], row["direction"]) for row in from_source["neighbors"]] == [(service, "outbound")]
    assert [(row["entity_id"], row["direction"]) for row in from_target["neighbors"]] == [(component, "inbound")]
    assert [row["entity_name"] for row in from_source["neighbors"]] == ["Service"]


def test_derived_neighbours_without_a_hop_count_derive_within_the_configured_bound(repo: Path) -> None:
    """The route's old default of one hop derived nothing at all: derivation composes from two hops up."""
    component, function, service = _chain(repo)
    client = _client()

    derived = client.get(f"/api/entities/{component}/neighbors?traversal=derived").json()
    direct = client.get(f"/api/entities/{component}/neighbors").json()

    assert [row["entity_id"] for row in derived["neighbors"]] == [service]
    assert direct["hops"] == {"1": [function]}
