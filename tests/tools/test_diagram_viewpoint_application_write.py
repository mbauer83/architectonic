"""Tests for the 'viewpoint' frontmatter parameter on artifact_create_diagram/
artifact_edit_diagram (WU-E6 — MCP exposure of ViewpointApplication).

WU-E4 already wired the read/parse/verify path (frontmatter schema property + verifier);
this covers the write path these tools now expose: format_diagram_puml persists a
'viewpoint:' block that parse_viewpoint_application (the same grammar the verifier uses)
reads back unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def test_create_diagram_dry_run_writes_viewpoint_frontmatter(repo: Path) -> None:
    result = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="Landscape",
        puml="@startuml\ntitle Landscape\nrectangle X\n@enduml\n",
        viewpoint={"slug": "motivation", "version": 2},
        dry_run=True,
        repo_root=str(repo),
    )
    content = str(result["content"])
    fm = yaml.safe_load(content.split("---\n")[1])
    assert fm["viewpoint"] == {"slug": "motivation", "version": 2}


def test_create_diagram_viewpoint_defaults_version_to_one(repo: Path) -> None:
    result = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="Landscape",
        puml="@startuml\ntitle Landscape\nrectangle X\n@enduml\n",
        viewpoint={"slug": "motivation"},
        dry_run=True,
        repo_root=str(repo),
    )
    fm = yaml.safe_load(str(result["content"]).split("---\n")[1])
    assert fm["viewpoint"] == {"slug": "motivation", "version": 1}


def test_create_diagram_rejects_malformed_viewpoint(repo: Path) -> None:
    with pytest.raises(ValueError, match="slug"):
        mcp.artifact_create_diagram(
            diagram_type="archimate-motivation",
            name="Landscape",
            puml="@startuml\ntitle Landscape\nrectangle X\n@enduml\n",
            viewpoint={"version": 1},
            dry_run=True,
            repo_root=str(repo),
        )


def test_edit_diagram_applies_viewpoint_to_existing_diagram(repo: Path) -> None:
    artifact_id = "ARC@1778000020.abc123.landscape"
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="Landscape",
        puml=(
            f"@startuml {artifact_id}\n!include ../_archimate-stereotypes.puml\n"
            "title Landscape\nrectangle X\n@enduml\n"
        ),
        artifact_id=artifact_id,
        dry_run=False,
        repo_root=str(repo),
        auto_include_stereotypes=False,
    )
    assert created["wrote"], created
    path = Path(str(created["path"]))
    assert "viewpoint" not in _read_fm(path)

    edited = mcp.artifact_edit_diagram(
        artifact_id=artifact_id,
        viewpoint={"slug": "motivation", "version": 3, "enforcement_override": "ghost"},
        dry_run=False,
        repo_root=str(repo),
    )
    assert edited["wrote"], edited
    fm = _read_fm(path)
    assert fm["viewpoint"] == {
        "slug": "motivation",
        "version": 3,
        "enforcement_override": "ghost",
    }


def test_edit_diagram_preserves_viewpoint_when_omitted(repo: Path) -> None:
    artifact_id = "ARC@1778000021.def456.landscape"
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="Landscape",
        puml=(
            f"@startuml {artifact_id}\n!include ../_archimate-stereotypes.puml\n"
            "title Landscape\nrectangle X\n@enduml\n"
        ),
        artifact_id=artifact_id,
        viewpoint={"slug": "motivation", "version": 1},
        dry_run=False,
        repo_root=str(repo),
        auto_include_stereotypes=False,
    )
    assert created["wrote"], created
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"

    edited = mcp.artifact_edit_diagram(
        artifact_id=artifact_id,
        name="Landscape (renamed)",
        dry_run=False,
        repo_root=str(repo),
    )
    assert edited["wrote"], edited
    fm = _read_fm(path)
    assert fm["viewpoint"] == {"slug": "motivation", "version": 1}
    assert fm["name"] == "Landscape (renamed)"
