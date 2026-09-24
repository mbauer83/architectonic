"""What a diagram says about its elements' icons is checked: references, styles, applicability, names."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import icon_file, write_icon

NODE_ICON = "ICO@1790000000.aks001.azure-kubernetes-service"
SERVICE_ICON = "ICO@1790000001.svc001.service"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    write_icon(root, icon_file(NODE_ICON, applies_to=("technology-node",)))
    write_icon(root, icon_file(SERVICE_ICON, applies_to=("application-service",)))
    return root


def _archimate(repo: Path, statements: dict) -> list[str]:
    node = mcp.artifact_create_entity(
        artifact_type="technology-node", name="Cluster", dry_run=False, repo_root=str(repo)
    )["artifact_id"]
    # "$node" in a statement stands for the entity created here, whose id the parameters cannot know.
    statements = {
        statement: {(node if key == "$node" else key): ref for key, ref in entries.items()}
        for statement, entries in statements.items()
    }
    result = mcp.artifact_create_diagram(
        diagram_type="archimate-technology", name="View", entity_ids=[str(node)],
        diagram_entities=statements, dry_run=True, repo_root=str(repo),
    )
    return [issue["code"] for issue in result["verification"]["issues"]]


def test_statements_that_hold_are_clean(repo: Path) -> None:
    assert _archimate(repo, {"display_icons": {"$node": NODE_ICON}, "type_icons": {"technology-node": NODE_ICON}}) == []


@pytest.mark.parametrize(
    ("statements", "code"),
    [
        ({"display_icons": {"$node": "ICO@1790000009.gone01"}}, "E364"),
        ({"display_icons": {"$node": "local:missing"}}, "E364"),
        ({"display_icons": {"$node": "not-an-icon"}}, "E364"),
        ({"display_icons": {"$node": {"icon": NODE_ICON, "style": "sticker"}}}, "E364"),
        ({"display_icons": {"$node": SERVICE_ICON}}, "W361"),
        ({"type_icons": {"technology-node": SERVICE_ICON}}, "W361"),
        ({"type_icons": {"technology-nod": NODE_ICON}}, "W362"),
    ],
    ids=["unknown-library-icon", "unknown-local-icon", "malformed", "unknown-style", "instance-not-applying",
         "type-not-applying", "unknown-type-name"],
)
def test_each_statement_that_does_not_hold_is_named(repo: Path, statements: dict, code: str) -> None:
    assert code in _archimate(repo, statements)


def test_a_style_the_type_does_not_draw_is_e365(repo: Path) -> None:
    result = mcp.artifact_create_diagram(
        diagram_type="c4-container", name="Orders", dry_run=True, repo_root=str(repo),
        diagram_entities={
            "software-system": [{"id": "sys", "label": "Orders"}],
            "container": [{"id": "db", "label": "DB"}],
            "display_icons": {"db": {"icon": NODE_ICON, "style": "figure"}},
        },
    )

    assert "E365" in [issue["code"] for issue in result["verification"]["issues"]]
