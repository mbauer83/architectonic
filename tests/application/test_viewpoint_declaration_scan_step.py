"""Tests for the viewpoints.yaml scan step: silent on absent/well-formed files, fires on
malformed YAML and on unknown-key/enum drift, never auto-migrates."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.viewpoint_declaration_scan import ViewpointDeclarationScanStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_WELL_FORMED = """\
viewpoints:
  - slug: platform-overview
    name: Platform Overview
    purpose: informing
    content: overview
"""


def _view(root: Path, content: str | None) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    if content is not None:
        (root / ".arch-repo" / "viewpoints.yaml").write_text(content, encoding="utf-8")
    return FilesystemRepoUpgradeView(root)


def test_silent_when_file_absent(tmp_path: Path) -> None:
    assert ViewpointDeclarationScanStep().detect(_view(tmp_path, None)) == []


def test_silent_on_well_formed_declarations(tmp_path: Path) -> None:
    assert ViewpointDeclarationScanStep().detect(_view(tmp_path, _WELL_FORMED)) == []


def test_fires_on_malformed_yaml(tmp_path: Path) -> None:
    view = _view(tmp_path, "viewpoints:\n  - slug: [unterminated\n")

    (finding,) = ViewpointDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-viewpoints:")
    assert finding.auto_migratable is False
    assert finding.manual_instructions is not None


def test_fires_on_unknown_key(tmp_path: Path) -> None:
    view = _view(
        tmp_path,
        "viewpoints:\n  - slug: platform-overview\n    not_a_real_key: oops\n",
    )

    (finding,) = ViewpointDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-viewpoints:")


def test_fires_on_invalid_purpose_enum(tmp_path: Path) -> None:
    view = _view(
        tmp_path,
        "viewpoints:\n  - slug: platform-overview\n    purpose: not-a-real-purpose\n",
    )

    (finding,) = ViewpointDeclarationScanStep().detect(view)

    assert finding.finding_id.startswith("malformed-viewpoints:")


_MALFORMED_TRACE = """\
viewpoints:
  - slug: coverage
    name: Coverage
    purpose: informing
    content: overview
    query:
      query_schema: 1
      trace_patterns:
        - name: motivation
          kind: not-a-real-kind
          applies_to: [goal]
          branches:
            g2o: {kind: stored-edge, connection: archimate-realization, direction: incoming, endpoint: {type: outcome}}
          leaf: {kind: none}
"""


def test_fires_on_malformed_trace_pattern_declaration(tmp_path: Path) -> None:
    # The ONE shared declaration detector already covers the trace grammar, since
    # trace_patterns parses through query_from_mapping — an unknown pattern kind is a finding,
    # not a silent load or a crash.
    (finding,) = ViewpointDeclarationScanStep().detect(_view(tmp_path, _MALFORMED_TRACE))

    assert finding.finding_id.startswith("malformed-viewpoints:")
    assert finding.auto_migratable is False


def test_apply_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    view = _view(tmp_path, "viewpoints:\n  - slug: [unterminated\n")
    registry = StepRegistry()
    registry.register(ViewpointDeclarationScanStep())

    report = apply_repository(
        view, FilesystemRepoUpgradeWriter(tmp_path), registry=registry, software_version="0.0.0-test"
    )

    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.touched_locations == frozenset()
