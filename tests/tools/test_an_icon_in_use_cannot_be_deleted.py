"""A library icon is deleted only once nothing shows it; until then the refusal names every user."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.write.icon import artifact_delete_icon
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


def _icon(repo: Path) -> str:
    return str(mcp.artifact_create_icon(
        name="Mark", attribution="Drawn here", content_base64=base64.b64encode(png_of()).decode(),
        source_format="png", dry_run=False, repo_root=str(repo),
    )["artifact_id"])


def test_an_icon_a_diagram_shows_is_refused_with_the_diagram_named(repo: Path) -> None:
    icon = _icon(repo)
    node = mcp.artifact_create_entity(artifact_type="technology-node", name="N", dry_run=False, repo_root=str(repo))
    diagram = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="View", entity_ids=[str(node["artifact_id"])],
        diagram_entities={"type_icons": {"technology-node": icon}}, dry_run=False, repo_root=str(repo),
    )

    refused = artifact_delete_icon(artifact_id=icon, dry_run=False, repo_root=str(repo))

    assert refused["ok"] is False and str(diagram["artifact_id"]) in refused["error"]
    assert (repo / "diagram-catalog" / "icons" / f"{icon}.md").exists()


def test_an_icon_nothing_shows_is_deleted(repo: Path) -> None:
    icon = _icon(repo)

    deleted = artifact_delete_icon(artifact_id=icon, dry_run=False, repo_root=str(repo))

    assert deleted["wrote"] is True and not (repo / "diagram-catalog" / "icons" / f"{icon}.md").exists()


def test_an_unknown_icon_says_so(repo: Path) -> None:
    assert artifact_delete_icon(artifact_id="ICO@1790000009.gone01", dry_run=False, repo_root=str(repo))["ok"] is False
