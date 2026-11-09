"""An attribute removed in the entity edit form is removed from the entity.

The write path patches `properties` and `attribute_types` key by key: an omitted key keeps its value,
and a key mapped to null is removed. The GUI form states an entity's attributes whole and left a
deleted row out of the body, which reads as "keep it" — so deleting an attribute on the entity page
saved, reported success, and changed nothing. The form now sends null for what it took away; these
tests pin that the REST surface accepts that for both maps, which `attribute_types` did not.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")


@pytest.fixture()
def rest_client(tmp_path: Path):
    from starlette.testclient import TestClient

    repo = tmp_path / "engagements" / "ENG-ATTRDEL" / "architecture-repository"
    (repo / "model").mkdir(parents=True)
    (repo / "diagram-catalog" / "diagrams").mkdir(parents=True)
    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    return TestClient(build_api_app(entities_router)), repo


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])


def _entity_with_two_attributes(repo: Path) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="requirement", name="Attribute Removal", summary="Carries two attributes",
        properties={"Rationale": "kept", "Retries": "3"}, attribute_types={"Retries": "integer"},
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _edit(client, artifact_id: str, **body: object) -> dict:
    response = client.patch(f"/api/entities/{artifact_id}", json={**body, "dry_run": False})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["wrote"] is True, result
    return result


def test_a_property_mapped_to_null_is_removed_and_its_neighbour_kept(rest_client) -> None:
    client, repo = rest_client
    artifact_id = _entity_with_two_attributes(repo)

    result = _edit(
        client, artifact_id,
        properties={"Rationale": "kept", "Retries": None}, attribute_types={"Retries": None},
    )

    written = Path(str(result["path"])).read_text(encoding="utf-8")
    assert "Retries" not in written
    assert "Rationale" in written and "kept" in written
    assert "Retries" not in (_frontmatter(Path(str(result["path"]))).get("attribute-types") or {})


def test_an_attribute_type_mapped_to_null_is_accepted_and_removed(rest_client) -> None:
    """The body used to type `attribute_types` as `dict[str, str]`, so this was a 422."""
    client, repo = rest_client
    artifact_id = _entity_with_two_attributes(repo)

    result = _edit(client, artifact_id, attribute_types={"Retries": None})

    assert "Retries" not in (_frontmatter(Path(str(result["path"]))).get("attribute-types") or {})
    assert "Retries" in Path(str(result["path"])).read_text(encoding="utf-8"), (
        "removing a type must not remove the attribute it typed"
    )


def test_omitting_a_property_still_keeps_it(rest_client) -> None:
    """The patch semantics the GUI fix relies on, stated so a change to them is seen here first."""
    client, repo = rest_client
    artifact_id = _entity_with_two_attributes(repo)

    result = _edit(client, artifact_id, properties={"Rationale": "changed"})

    written = Path(str(result["path"])).read_text(encoding="utf-8")
    assert "changed" in written and "Retries" in written
