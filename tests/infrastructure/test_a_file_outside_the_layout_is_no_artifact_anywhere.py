"""The save dialog and `artifact_verify` read a path's kind the one way the layout gives it.

The save dialog knew only the top-level `model/`, so an entity under `projects/<slug>/model/` — where
every entity of this repository lives — was not listed; `artifact_verify` verified any path it did
not recognise as an entity.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from src.infrastructure.mcp.artifact_mcp.verify_tools import artifact_verify
from src.infrastructure.rest.routers.sync.changes import list_changes

_ENTITY = (
    "---\nartifact-id: REQ@1.aaaa.probe\nartifact-type: requirement\nname: Probe\nversion: 0.1.0\n"
    "status: draft\nlast-updated: '2026-01-01'\n---\n\n## Probe\n"
)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    _write(root, ".gitkeep", "")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", ".")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base")
    return root


def test_the_save_dialog_lists_an_entity_under_a_project_and_not_a_readme(repo: Path) -> None:
    _write(repo, "projects/core/model/motivation/requirement/REQ@1.aaaa.probe.md", _ENTITY)
    _write(repo, "projects/core/NOTES.md", _ENTITY.replace("REQ@1.aaaa.probe", "REQ@2.bbbb.stray"))
    _write(repo, "README.md", "# readme\n")

    listed = {entry["artifact_id"]: entry["record_type"] for entry in list_changes(repo)}

    assert listed == {"REQ@1.aaaa.probe": "entity"}


def test_a_rendered_picture_is_still_saved_with_its_diagram(repo: Path) -> None:
    _write(repo, "diagram-catalog/rendered/core/ARC@1.aaaa.view.svg", "<svg/>")

    assert [e["record_type"] for e in list_changes(repo)] == ["diagram"]


def test_verifying_a_file_the_layout_gives_no_kind_is_refused_with_the_way_forward(repo: Path) -> None:
    readme = _write(repo, "README.md", _ENTITY)

    result = asyncio.run(artifact_verify(str(readme), repo_root=str(repo), repo_scope="engagement"))

    assert result["ok"] is False and "file_type" in result["message"]
