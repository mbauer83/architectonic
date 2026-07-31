"""`edit_entity` canonicalizes a short artifact id before it renders anything.

`find_file_by_id` resolves both the full id (``PREFIX@epoch.random.slug``) and the short,
rename-stable one (``PREFIX@epoch.random``) — see test_diagram_short_id.py for the sibling
case. Whichever form the caller passes, the frontmatter has to record the full id: the
verifier rejects the short form as malformed (E101), so rendering it back would decline the
write, and the rename path rsplits the slug off to build its target.

The canonicalization belongs in the use case rather than in each adapter, because the MCP
tools expand ids themselves (``expand_artifact_id``) and the REST router does not. These
tests pin both surfaces.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router
from src.infrastructure.mcp import mcp_artifact_server as mcp

httpx = pytest.importorskip("httpx")


def _short(artifact_id: str) -> str:
    """PREFIX@epoch.random.slug → PREFIX@epoch.random."""
    prefix, _, _slug = artifact_id.rpartition(".")
    assert prefix, artifact_id
    return prefix


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-SHORTID" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def rest_client(repo: Path):
    from starlette.testclient import TestClient

    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    app = FastAPI()
    app.include_router(entities_router)
    return TestClient(app), repo


def _create(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="requirement", name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


class TestUseCaseCanonicalizesShortIds:
    def test_short_id_edit_writes_the_full_id_into_frontmatter(self, repo: Path) -> None:
        full_id = _create(repo, "Short Id Target")

        result = mcp.artifact_edit_entity(
            artifact_id=_short(full_id),
            summary="Edited through the short id",
            dry_run=False,
            repo_root=str(repo),
        )

        assert result["wrote"] is True, result
        assert result["artifact_id"] == full_id
        written = Path(str(result["path"]))
        assert written.name == f"{full_id}.md"
        assert _frontmatter(written)["artifact-id"] == full_id

    def test_short_id_edit_verifies_clean(self, repo: Path) -> None:
        """A frontmatter id that does not match TYPE@epoch.random.name fails E101."""
        full_id = _create(repo, "Short Id Verifies")

        result = mcp.artifact_edit_entity(
            artifact_id=_short(full_id),
            summary="Still valid",
            dry_run=False,
            repo_root=str(repo),
        )

        verification = result["verification"]
        assert verification["valid"] is True, verification
        assert verification["issues"] == []

    def test_short_id_rename_keeps_the_random_segment(self, repo: Path) -> None:
        """_resolve_target_identity rsplits the slug off the id to build the rename
        target, so it needs the full form to keep the random segment."""
        full_id = _create(repo, "Rename From Short")
        stable_prefix = _short(full_id)

        result = mcp.artifact_edit_entity(
            artifact_id=stable_prefix,
            name="Renamed Via Short Id",
            dry_run=False,
            repo_root=str(repo),
        )

        new_id = str(result["artifact_id"])
        assert result["wrote"] is True, result
        assert new_id == f"{stable_prefix}.renamed-via-short-id"
        assert _frontmatter(Path(str(result["path"])))["artifact-id"] == new_id


class TestRestSurfaceAcceptsShortIds:
    def test_rest_edit_with_a_short_id_writes(self, rest_client) -> None:
        client, repo = rest_client
        full_id = _create(repo, "Rest Short Id")

        response = client.patch(
            f"/api/entities/{_short(full_id)}",
            json={
                "properties": {"Source Repository": "https://example.invalid/repo"},
                "dry_run": False,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["wrote"] is True, body
        assert body["artifact_id"] == full_id
        assert body["verification"]["valid"] is True, body["verification"]

        written = Path(str(body["path"]))
        assert _frontmatter(written)["artifact-id"] == full_id
        assert "https://example.invalid/repo" in written.read_text(encoding="utf-8")
