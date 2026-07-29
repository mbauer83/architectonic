"""Tests for the diagram/matrix viewpoint-application scan step: silent on diagrams with no
`viewpoint:` key and on well-formed applications, fires on a malformed value (the same shape
`parse_viewpoint_application` raises loudly on), scoped to diagram-typed frontmatter only
(mirrors `MultiplicityRenameStep`'s own `artifact-type == diagram` scoping), never
auto-migrates."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.viewpoint_application_scan import ViewpointApplicationScanStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)


def _write_diagram(root: Path, frontmatter_body: str) -> None:
    path = root / "diagram-catalog/diagrams/uncategorized/D1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\nartifact-id: DIA@1.abc.d1\nartifact-type: diagram\nname: D1\n"
        f"{frontmatter_body}---\n@startuml\n@enduml\n"
    )
    path.write_text(content, encoding="utf-8")


def _view(root: Path) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return FilesystemRepoUpgradeView(root)


def test_silent_when_no_viewpoint_key(tmp_path: Path) -> None:
    _write_diagram(tmp_path, "")

    assert ViewpointApplicationScanStep().detect(_view(tmp_path)) == []


def test_silent_on_well_formed_application(tmp_path: Path) -> None:
    _write_diagram(tmp_path, "viewpoint:\n  slug: platform-overview\n  version: 1\n")

    assert ViewpointApplicationScanStep().detect(_view(tmp_path)) == []


def test_fires_on_missing_slug(tmp_path: Path) -> None:
    _write_diagram(tmp_path, "viewpoint:\n  version: 1\n")

    (finding,) = ViewpointApplicationScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("malformed-viewpoint-application:")
    assert finding.auto_migratable is False
    assert finding.manual_instructions is not None


def test_fires_on_unknown_enforcement_override(tmp_path: Path) -> None:
    _write_diagram(
        tmp_path,
        "viewpoint:\n  slug: platform-overview\n  version: 1\n  enforcement_override: not-a-real-mode\n",
    )

    (finding,) = ViewpointApplicationScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("malformed-viewpoint-application:")


def test_silent_on_non_diagram_entity_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "model/motivation/requirement/REQ@1.abc.name.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\nartifact-id: REQ@1.abc.name\nartifact-type: requirement\nname: X\n"
        "viewpoint: not-even-a-mapping\n---\nbody\n"
    )
    path.write_text(content, encoding="utf-8")

    assert ViewpointApplicationScanStep().detect(_view(tmp_path)) == []


def test_apply_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    _write_diagram(tmp_path, "viewpoint:\n  version: 1\n")
    view = _view(tmp_path)
    registry = StepRegistry()
    registry.register(ViewpointApplicationScanStep())

    report = apply_repository(
        view, FilesystemRepoUpgradeWriter(tmp_path), registry=registry, software_version="0.0.0-test"
    )

    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.touched_locations == frozenset()
