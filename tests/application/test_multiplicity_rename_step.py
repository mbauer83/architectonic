"""Tests for the multiplicity-rename step: detect/apply/idempotence, scoping to
diagram frontmatter only, multi-entry rewrite, and the step-conformance harness."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.multiplicity_rename import MultiplicityRenameStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

_DIAGRAM_WITH_LEGACY_KEY = """\
---
artifact-id: DIA@1.abc.d1
artifact-type: diagram
name: D1
connections:
  - artifact_id: CONN@1.abc.c1
    include_cardinality: true
    label: "foo"
  - artifact_id: CONN@1.abc.c2
    include_description: true
extra-unknown-field: keep-me
---
@startuml
@enduml
"""


def _registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(MultiplicityRenameStep())
    return reg


def _setup(tmp_path: Path, content: str, rel: str = "diagram-catalog/diagrams/D1.md") -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    (tmp_path / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return path


def test_detects_legacy_key_in_diagram_connections(tmp_path: Path) -> None:
    _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY)
    view = FilesystemRepoUpgradeView(tmp_path)

    (finding,) = MultiplicityRenameStep().detect(view)

    assert finding.auto_migratable is True
    assert "1 diagram connections entry" in finding.description


def test_detects_legacy_key_in_puml_diagram_file(tmp_path: Path) -> None:
    """Regression: real ArchiMate/sequence/activity/c4 diagrams are persisted as `.puml`,
    not `.md` (only matrix-type diagrams use `.md`) — a `.md`-only glob would silently
    never find the one place this legacy key actually lives in practice."""
    _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY, rel="diagram-catalog/diagrams/D1.puml")
    view = FilesystemRepoUpgradeView(tmp_path)

    (finding,) = MultiplicityRenameStep().detect(view)

    assert finding.location == "diagram-catalog/diagrams/D1.puml"


def test_silent_when_no_legacy_key(tmp_path: Path) -> None:
    content = _DIAGRAM_WITH_LEGACY_KEY.replace("include_cardinality: true", "include_multiplicity: true")
    _setup(tmp_path, content)
    view = FilesystemRepoUpgradeView(tmp_path)

    assert MultiplicityRenameStep().detect(view) == []


def test_silent_on_non_diagram_frontmatter(tmp_path: Path) -> None:
    content = _DIAGRAM_WITH_LEGACY_KEY.replace("artifact-type: diagram", "artifact-type: requirement")
    _setup(tmp_path, content)
    view = FilesystemRepoUpgradeView(tmp_path)

    assert MultiplicityRenameStep().detect(view) == []


def test_apply_renames_only_the_legacy_key_and_preserves_everything_else(tmp_path: Path) -> None:
    path = _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    findings = MultiplicityRenameStep().detect(view)
    MultiplicityRenameStep().apply(view, writer, findings)

    rewritten = path.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(rewritten.split("---\n")[1])
    assert frontmatter["connections"][0]["include_multiplicity"] is True
    assert "include_cardinality" not in frontmatter["connections"][0]
    assert frontmatter["connections"][1] == {"artifact_id": "CONN@1.abc.c2", "include_description": True}
    assert frontmatter["extra-unknown-field"] == "keep-me"
    assert "@startuml" in rewritten and "@enduml" in rewritten


def test_apply_is_idempotent(tmp_path: Path) -> None:
    _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)
    registry = _registry()

    first = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")
    second = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")

    assert first.applied_steps_after == ("d9-multiplicity-rename",)
    assert second.results == ()
    assert second.unapplied_required_steps == ()


def test_dry_run_never_mutates(tmp_path: Path) -> None:
    path = _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY)
    view = FilesystemRepoUpgradeView(tmp_path)
    before = path.read_text(encoding="utf-8")

    report = evaluate_repository(view, registry=_registry(), software_version="0.0.0-test")

    assert report.unapplied_required_steps == ("d9-multiplicity-rename",)
    assert path.read_text(encoding="utf-8") == before


def test_multiple_diagrams_all_migrated(tmp_path: Path) -> None:
    _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY, rel="diagram-catalog/diagrams/D1.md")
    _setup(
        tmp_path,
        _DIAGRAM_WITH_LEGACY_KEY.replace("DIA@1.abc.d1", "DIA@1.abc.d2").replace("name: D1", "name: D2"),
        rel="diagram-catalog/diagrams/D2.md",
    )
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    report = apply_repository(view, writer, registry=_registry(), software_version="0.0.0-test")

    assert len(report.results) == 2
    assert all(r.outcome == "applied" for r in report.results)
    for rel in ("diagram-catalog/diagrams/D1.md", "diagram-catalog/diagrams/D2.md"):
        assert "include_cardinality" not in (tmp_path / rel).read_text(encoding="utf-8")


def test_step_conformance_harness(tmp_path: Path) -> None:
    _setup(tmp_path, _DIAGRAM_WITH_LEGACY_KEY)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    assert_step_preserves_unknown_content(
        MultiplicityRenameStep(),
        view,
        writer,
        location="diagram-catalog/diagrams/D1.md",
        unknown_marker="extra-unknown-field: keep-me",
    )
