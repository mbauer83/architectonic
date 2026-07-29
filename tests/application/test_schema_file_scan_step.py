"""Tests for the schema-file scan step: silent on absent/well-formed schema files, fires on
malformed JSON across all three naming conventions, never auto-migrates."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.schema_file_scan import SchemaFileScanStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_VALID_SCHEMA = '{"type": "object", "properties": {"name": {"type": "string"}}}'


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _view(root: Path) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return FilesystemRepoUpgradeView(root)


def test_silent_when_no_schemata_dir(tmp_path: Path) -> None:
    assert SchemaFileScanStep().detect(_view(tmp_path)) == []


def test_silent_on_well_formed_schemata(tmp_path: Path) -> None:
    root = tmp_path
    _write(root, ".arch-repo/schemata/attributes.requirement.schema.json", _VALID_SCHEMA)
    _write(root, ".arch-repo/schemata/attributes.requirement.confidential-data.schema.json", _VALID_SCHEMA)
    _write(root, ".arch-repo/schemata/frontmatter.entity.schema.json", _VALID_SCHEMA)
    _write(root, ".arch-repo/schemata/connection-metadata.assignment.schema.json", _VALID_SCHEMA)

    assert SchemaFileScanStep().detect(_view(root)) == []


def test_fires_on_malformed_json_base_profile(tmp_path: Path) -> None:
    root = tmp_path
    _write(root, ".arch-repo/schemata/attributes.requirement.schema.json", "{not valid json")

    (finding,) = SchemaFileScanStep().detect(_view(root))

    assert finding.finding_id.startswith("malformed-schema-json:")
    assert finding.auto_migratable is False
    assert finding.manual_instructions is not None


def test_fires_on_malformed_json_attachment_and_connection_metadata(tmp_path: Path) -> None:
    root = tmp_path
    _write(root, ".arch-repo/schemata/attributes.requirement.confidential-data.schema.json", "[1, 2,")
    _write(root, ".arch-repo/schemata/connection-metadata.assignment.schema.json", "{'single': 'quotes'}")

    findings = SchemaFileScanStep().detect(_view(root))

    assert {f.location for f in findings} == {
        ".arch-repo/schemata/attributes.requirement.confidential-data.schema.json",
        ".arch-repo/schemata/connection-metadata.assignment.schema.json",
    }


def test_apply_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    root = tmp_path
    _write(root, ".arch-repo/schemata/attributes.requirement.schema.json", "{not valid json")
    view = _view(root)
    registry = StepRegistry()
    registry.register(SchemaFileScanStep())

    report = apply_repository(view, FilesystemRepoUpgradeWriter(root), registry=registry, software_version="0.0.0-test")

    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.touched_locations == frozenset()
