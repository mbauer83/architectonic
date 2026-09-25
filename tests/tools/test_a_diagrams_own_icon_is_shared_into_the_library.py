"""An icon a diagram holds for itself is moved into the library, and the diagram names it there (D11)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.write.icon import artifact_share_icon
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of

ATTRIBUTION = "Drawn here; no third-party mark"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


def _diagram_with_its_own_icon(repo: Path, colour: tuple[int, int, int, int] = (200, 40, 40, 255)) -> tuple[str, Path]:
    node = str(mcp.artifact_create_entity(
        artifact_type="technology-node", name="N", dry_run=False, repo_root=str(repo),
    )["artifact_id"])
    upload = {"name": "Logo", "content_base64": base64.b64encode(png_of(colour)).decode(), "source_format": "png"}
    diagram = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="View", entity_ids=[node],
        diagram_entities={"display_icons": {node: "local:logo"}, "icons": {"logo": upload}},
        dry_run=False, repo_root=str(repo),
    )
    assert diagram["wrote"] is True, diagram
    return node, Path(str(diagram["path"]))


def _entities(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))["diagram-entities"]  # type: ignore[return-value]


def test_the_icon_joins_the_library_and_the_diagram_names_it_there(repo: Path) -> None:
    node, path = _diagram_with_its_own_icon(repo)
    diagram_id = parse_frontmatter(path.read_text(encoding="utf-8"))["artifact-id"]

    shared = artifact_share_icon(
        diagram_id=str(diagram_id), icon_key="logo", attribution=ATTRIBUTION, dry_run=False, repo_root=str(repo),
    )

    icon_id = str(shared["artifact_id"])
    assert shared["wrote"] is True and (repo / "diagram-catalog" / "icons" / f"{icon_id}.md").exists()
    entities = _entities(path)
    assert entities["display_icons"] == {node: stable_id(icon_id)}
    assert "icons" not in entities, "the diagram's own copy is dropped once nothing names it"


def test_a_picture_the_library_holds_is_named_not_copied(repo: Path) -> None:
    held = mcp.artifact_create_icon(
        name="Held", attribution=ATTRIBUTION, content_base64=base64.b64encode(png_of((200, 40, 40, 255))).decode(),
        source_format="png", dry_run=False, repo_root=str(repo),
    )["artifact_id"]
    node, path = _diagram_with_its_own_icon(repo)
    diagram_id = parse_frontmatter(path.read_text(encoding="utf-8"))["artifact-id"]

    shared = artifact_share_icon(
        diagram_id=str(diagram_id), icon_key="logo", attribution=ATTRIBUTION, dry_run=False, repo_root=str(repo),
    )

    assert shared["wrote"] is True and str(shared["artifact_id"]) == str(held)
    assert _entities(path)["display_icons"] == {node: stable_id(str(held))}
    assert len(list((repo / "diagram-catalog" / "icons").glob("*.md"))) == 1


def test_an_icon_the_diagram_does_not_hold_says_so(repo: Path) -> None:
    _node, path = _diagram_with_its_own_icon(repo)
    diagram_id = parse_frontmatter(path.read_text(encoding="utf-8"))["artifact-id"]

    refused = artifact_share_icon(
        diagram_id=str(diagram_id), icon_key="other", attribution=ATTRIBUTION, repo_root=str(repo),
    )

    assert refused["ok"] is False


def test_a_share_without_attribution_writes_nothing(repo: Path) -> None:
    _node, path = _diagram_with_its_own_icon(repo)
    before = path.read_text(encoding="utf-8")
    diagram_id = parse_frontmatter(before)["artifact-id"]

    refused = artifact_share_icon(
        diagram_id=str(diagram_id), icon_key="logo", attribution=" ", dry_run=False, repo_root=str(repo),
    )

    assert refused["wrote"] is False and path.read_text(encoding="utf-8") == before
    assert not list((repo / "diagram-catalog").glob("icons/*.md"))
