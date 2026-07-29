"""Tests for the shared frontmatter-candidate-file discovery helper: must find both `.md`
and `.puml` content regardless of directory layout (top-level model/diagram-catalog AND
per-project projects/*/model, projects/*/diagram-catalog can both exist)."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView


def _write(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nartifact-type: diagram\n---\nbody\n", encoding="utf-8")


def test_finds_both_extensions_across_top_level_and_per_project_layout(tmp_path: Path) -> None:
    _write(tmp_path, "model/business/ENT@1.abc.x.md")
    _write(tmp_path, "diagram-catalog/diagrams/D1.puml")
    _write(tmp_path, "diagram-catalog/diagrams/M1.md")
    _write(tmp_path, "projects/foo/model/business/ENT@2.abc.y.md")
    _write(tmp_path, "projects/foo/diagram-catalog/diagrams/D2.puml")
    _write(tmp_path, "diagram-catalog/rendered/D1.svg")  # rendered output, not source — must be excluded

    files = list_frontmatter_candidate_files(FilesystemRepoUpgradeView(tmp_path))

    assert files == sorted(
        [
            "diagram-catalog/diagrams/D1.puml",
            "diagram-catalog/diagrams/M1.md",
            "model/business/ENT@1.abc.x.md",
            "projects/foo/diagram-catalog/diagrams/D2.puml",
            "projects/foo/model/business/ENT@2.abc.y.md",
        ]
    )
