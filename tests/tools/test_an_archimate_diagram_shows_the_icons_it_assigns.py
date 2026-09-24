"""An ArchiMate diagram created with icon assignments draws each icon where its element's glyph sits."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.puml_directive_policy import find_unsafe_puml_directives
from src.application.puml_icon_header import BLOCK_BEGIN, icon_key
from src.domain.icons.render_form import render_digest
from src.infrastructure.mcp import mcp_artifact_server as mcp
from tests.support.icon_files import icon_file, png_of, write_icon

AKS = "ICO@1790000000.aks001.azure-kubernetes-service"
PICTURE = png_of((0, 120, 212, 255), size=(64, 64))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    write_icon(root, icon_file(AKS, png=PICTURE, applies_to=("technology-node",)))
    return root


def _node(repo: Path, name: str) -> str:
    created = mcp.artifact_create_entity(artifact_type="technology-node", name=name, dry_run=False, repo_root=str(repo))
    return str(created["artifact_id"])


def _create(repo: Path, entity_ids: list[str], diagram_entities: dict) -> dict:
    return mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="Cluster view", entity_ids=entity_ids,
        diagram_entities=diagram_entities, dry_run=False, repo_root=str(repo),
    )


def test_a_type_assignment_draws_the_icon_on_every_element_of_that_type(repo: Path) -> None:
    first, second = _node(repo, "Cluster A"), _node(repo, "Cluster B")

    result = _create(repo, [first, second], {"type_icons": {"technology-node": AKS}})

    body = Path(str(result["path"])).read_text(encoding="utf-8")
    key = icon_key(render_digest(PICTURE))
    assert body.count(f"<img:${key}{{scale=") == 2
    assert BLOCK_BEGIN in body and body.count(f"!${key} =") == 1
    assert find_unsafe_puml_directives(body) == []
    assert result["verification"]["valid"] is True, result["verification"]


def test_an_instance_assignment_draws_only_on_that_instance(repo: Path) -> None:
    first, second = _node(repo, "Cluster A"), _node(repo, "Cluster B")

    result = _create(repo, [first, second], {"display_icons": {first: AKS}})

    body = Path(str(result["path"])).read_text(encoding="utf-8")
    shows_icon = {
        name: "<img:$" in line
        for line in body.splitlines()
        for name in ("Cluster A", "Cluster B")
        if line.lstrip().startswith("rectangle") and name in line
    }
    assert shows_icon == {"Cluster A": True, "Cluster B": False}


def test_an_icon_for_another_type_leaves_the_glyph(repo: Path) -> None:
    write_icon(repo, icon_file("ICO@1790000001.svc001.x", applies_to=("application-service",)))
    node = _node(repo, "Cluster A")

    result = _create(repo, [node], {"display_icons": {node: "ICO@1790000001.svc001"}})

    body = Path(str(result["path"])).read_text(encoding="utf-8")
    assert "<img:$" not in body and BLOCK_BEGIN not in body and "<$archimate_" in body
