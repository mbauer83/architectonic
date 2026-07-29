"""Tests for diagram-collection re-homing via artifact_edit_diagram(group=...).

Covers the WU-C3 tool gap: artifact_edit_diagram previously had no way to move an
existing diagram into a diagram-collection group (artifact_edit_entity already
supported this for entities via its own `group` param). edit_diagram/
commit_diagram_write in _diagram_group_move.py add the delegation; these tests
are the regression coverage for that fix plus a contract test on the new
group-move helper itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _diagram_content(artifact_id: str, name: str) -> str:
    slug = name.lower().replace(" ", "-")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  software-system:
  - id: sys
    label: MySystem
---
@startuml {slug}
title {name}
@enduml
"""


def _make_standalone_diagram(repo: Path, artifact_id: str, name: str = "Standalone") -> Path:
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(_diagram_content(artifact_id, name), encoding="utf-8")
    return path


def _fake_rendered_outputs(repo: Path, artifact_id: str) -> tuple[Path, Path]:
    rendered_dir = repo / "diagram-catalog" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    png = rendered_dir / f"{artifact_id}.png"
    svg = rendered_dir / f"{artifact_id}.svg"
    png.write_bytes(b"fake-png")
    svg.write_text("<svg/>", encoding="utf-8")
    return png, svg


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


# ---------------------------------------------------------------------------
# artifact_edit_diagram(group=...) — MCP surface
# ---------------------------------------------------------------------------


def test_edit_diagram_group_relocates_source_file(repo: Path) -> None:
    artifact_id = "DIA@1778000001.tgrp.standalone"
    old_path = _make_standalone_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group="landing-zone", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    new_path = repo / "diagram-catalog" / "diagrams" / "landing-zone" / f"{artifact_id}.puml"
    assert new_path.exists()
    assert not old_path.exists()
    assert _read_fm(new_path)["artifact-id"] == artifact_id


def test_edit_diagram_group_relocates_rendered_outputs(repo: Path) -> None:
    artifact_id = "DIA@1778000002.tgrp.rendered"
    _make_standalone_diagram(repo, artifact_id)
    old_png, old_svg = _fake_rendered_outputs(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group="landing-zone", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    assert not old_png.exists()
    assert not old_svg.exists()


def test_edit_diagram_group_dry_run_previews_without_moving(repo: Path) -> None:
    artifact_id = "DIA@1778000003.tgrp.preview"
    old_path = _make_standalone_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group="landing-zone", dry_run=True, repo_root=str(repo),
    )

    assert not result["wrote"]
    assert old_path.exists()
    new_path = repo / "diagram-catalog" / "diagrams" / "landing-zone" / f"{artifact_id}.puml"
    assert not new_path.exists()
    assert any("Will move diagram to group" in w for w in result.get("warnings", []))


def test_edit_diagram_group_noop_when_already_in_group(repo: Path) -> None:
    artifact_id = "DIA@1778000004.tgrp.noop"
    old_path = _make_standalone_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group=UNCATEGORIZED, dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    assert old_path.exists()
    assert not any("Moved diagram to group" in w for w in result.get("warnings", []))


def test_edit_diagram_omitting_group_preserves_current_location(repo: Path) -> None:
    """Regression: editing an unrelated field must not implicitly move the diagram."""
    artifact_id = "DIA@1778000005.tgrp.unrelated"
    old_path = _make_standalone_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, name="Renamed Title", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    assert old_path.exists()


# ---------------------------------------------------------------------------
# commit_diagram_write / _resolve_diagram_group_path — contract tests
# ---------------------------------------------------------------------------


def test_resolve_diagram_group_path_returns_current_path_when_group_none(repo: Path) -> None:
    from src.infrastructure.write.artifact_write._diagram_group_move import _resolve_diagram_group_path

    current = repo / "diagram-catalog" / "diagrams" / "DIA@1.a.x.puml"
    resolved = _resolve_diagram_group_path(
        repo_root=repo, current_path=current, artifact_id="DIA@1.a.x",
        diagram_type="c4-container", tlp=None, group=None,
    )
    assert resolved == current


def test_resolve_diagram_group_path_nests_under_collection(repo: Path) -> None:
    from src.infrastructure.write.artifact_write._diagram_group_move import _resolve_diagram_group_path

    current = repo / "diagram-catalog" / "diagrams" / "DIA@1.a.x.puml"
    resolved = _resolve_diagram_group_path(
        repo_root=repo, current_path=current, artifact_id="DIA@1.a.x",
        diagram_type="c4-container", tlp=None, group="landing-zone",
    )
    assert resolved == repo / "diagram-catalog" / "diagrams" / "landing-zone" / "DIA@1.a.x.puml"
