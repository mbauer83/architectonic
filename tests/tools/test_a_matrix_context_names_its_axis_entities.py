"""A matrix's context lists the entities on its axes (B90).

The context read found a diagram's members by the aliases its PlantUML body declares. A matrix is a
Markdown table with no such body, so the read answered `entities: 0` for every matrix and the viewer's
sidebar said "ENTITIES 0" beside a full grid. The axes (`from-entity-ids` / `to-entity-ids`) are the
matrix's members; they are read by the one reader of those keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo_and_client(tmp_path: Path) -> Any:
    from starlette.testclient import TestClient

    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.rest.routers import state as gui_state
    from src.infrastructure.rest.routers.diagrams import router as diagrams_router
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults
    from tests.support.api_app import build_api_app

    root = tmp_path / "engagements" / "ENG-MAT" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    ensure_arch_repo_defaults(root)
    with shared_artifact_index([root]) as index:
        gui_state.init_state(ArtifactRepository(index), root, None, admin_mode=False)
        yield root, TestClient(build_api_app(diagrams_router.router))


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}", dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def test_every_axis_entity_is_in_the_context(repo_and_client) -> None:  # noqa: ANN001
    repo, client = repo_and_client
    rows = [_entity(repo, "requirement", name) for name in ("Fast Authoring", "Safe Writes")]
    columns = [_entity(repo, "outcome", name) for name in ("Less Overhead", "More Coherence")]
    created = mcp.artifact_create_matrix(
        name="What the system must do", matrix_markdown="| | |\n|---|---|\n",
        from_entity_ids=rows, to_entity_ids=columns, dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created

    response = client.get(f"/api/diagrams/{created['artifact_id']}/context")

    assert response.status_code == 200, response.text
    listed = {entity["artifact_id"] for entity in response.json()["entities"]}
    assert set(rows) | set(columns) <= listed
