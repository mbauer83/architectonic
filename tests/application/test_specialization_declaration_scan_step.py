"""Tests for the specializations.yaml scan step: silent on absent/well-formed files,
fires on malformed YAML and on a malformed catalog shape, never auto-migrates."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.specialization_declaration_scan import (
    SpecializationDeclarationScanStep,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_WELL_FORMED = """\
specializations:
  entity:
    business-object:
      - slug: confidential-data
        name: Confidential Data
"""


def _view(root: Path, content: str | None) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    if content is not None:
        (root / ".arch-repo" / "specializations.yaml").write_text(content, encoding="utf-8")
    return FilesystemRepoUpgradeView(root)


def test_silent_when_file_absent(tmp_path: Path) -> None:
    assert SpecializationDeclarationScanStep().detect(_view(tmp_path, None)) == []


def test_silent_on_well_formed_declarations(tmp_path: Path) -> None:
    assert SpecializationDeclarationScanStep().detect(_view(tmp_path, _WELL_FORMED)) == []


def test_fires_on_malformed_yaml(tmp_path: Path) -> None:
    view = _view(tmp_path, "specializations:\n  entity: [unterminated\n")

    (finding,) = SpecializationDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-specializations:")
    assert finding.auto_migratable is False
    assert finding.manual_instructions is not None


def test_fires_on_non_mapping_top_level(tmp_path: Path) -> None:
    view = _view(tmp_path, "- just\n- a\n- list\n")

    (finding,) = SpecializationDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-specializations:")


def test_fires_on_entry_missing_required_slug(tmp_path: Path) -> None:
    view = _view(
        tmp_path,
        "specializations:\n  entity:\n    business-object:\n      - name: No Slug Here\n",
    )

    (finding,) = SpecializationDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-specializations:")


def test_apply_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    view = _view(tmp_path, "specializations:\n  entity: [unterminated\n")
    registry = StepRegistry()
    registry.register(SpecializationDeclarationScanStep())

    report = apply_repository(
        view, FilesystemRepoUpgradeWriter(tmp_path), registry=registry, software_version="0.0.0-test"
    )

    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.touched_locations == frozenset()
