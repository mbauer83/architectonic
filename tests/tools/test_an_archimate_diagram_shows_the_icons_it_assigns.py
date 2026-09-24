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


def _body_of(result: dict) -> str:
    return Path(str(result["path"])).read_text(encoding="utf-8").split("\n---\n", 1)[1]


@pytest.mark.parametrize("manual_layout", [False, True], ids=["kept", "manual-layout"])
def test_a_kept_body_gains_and_loses_an_icon_touching_only_that_declaration(repo: Path, manual_layout: bool) -> None:
    first, second = _node(repo, "Cluster A"), _node(repo, "Cluster B")
    created = _create(repo, [first, second], {})
    diagram_id = str(created["artifact_id"])
    # The body as an edit leaves it: the first edit states the refreshed header (backlog B72).
    original = _body_of(
        mcp.artifact_edit_diagram(artifact_id=diagram_id, name="Cluster view", dry_run=False, repo_root=str(repo))
    )

    gained = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, diagram_entities={"display_icons": {first: AKS}},
        manual_layout=manual_layout or None, dry_run=False, repo_root=str(repo),
    )
    with_icon = _body_of(gained)
    changed = [line for line in with_icon.splitlines() if line not in original.splitlines()]
    assert gained["verification"]["valid"] is True, gained["verification"]
    assert any("Cluster A" in line and "<img:$" in line for line in changed)
    assert all("Cluster B" not in line for line in changed)

    lost = mcp.artifact_edit_diagram(
        artifact_id=diagram_id, diagram_entities={}, dry_run=False, repo_root=str(repo),
    )
    assert _body_of(lost) == original
