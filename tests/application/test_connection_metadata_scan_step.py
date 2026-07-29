"""Tests for the connection-metadata scan step: silent on absent/well-formed metadata
blocks (and on connections with no metadata block at all), fires on a metadata fence that
fails to parse as a mapping, never auto-migrates. This is the genuinely silent gap: today
neither `parse_connection_declarations` nor the live verifier's schema check surfaces a
malformed block at all."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.connection_metadata_scan import ConnectionMetadataScanStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_OUTGOING_HEADER = (
    "---\nsource-entity: REQ@1.abc.name\nversion: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n"
)


def _write_outgoing(root: Path, body: str) -> None:
    path = root / "model/motivation/requirement/REQ@1.abc.name.outgoing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_OUTGOING_HEADER + body, encoding="utf-8")


def _view(root: Path) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return FilesystemRepoUpgradeView(root)


def test_silent_on_connection_without_metadata_block(tmp_path: Path) -> None:
    _write_outgoing(tmp_path, "### assignment → REQ@2.def.other\n\nPlain description, no metadata block.\n")

    assert ConnectionMetadataScanStep().detect(_view(tmp_path)) == []


def test_silent_on_well_formed_metadata_block(tmp_path: Path) -> None:
    _write_outgoing(
        tmp_path,
        "### assignment → REQ@2.def.other\n\n```yaml\nspecialization: owns\n```\n\nDescription text.\n",
    )

    assert ConnectionMetadataScanStep().detect(_view(tmp_path)) == []


def test_fires_on_malformed_yaml_metadata_block(tmp_path: Path) -> None:
    _write_outgoing(
        tmp_path,
        "### assignment → REQ@2.def.other\n\n```yaml\nspecialization: [unterminated\n```\n\nDescription.\n",
    )

    (finding,) = ConnectionMetadataScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("malformed-connection-metadata:")
    assert finding.auto_migratable is False
    assert finding.manual_instructions is not None


def test_fires_on_non_mapping_metadata_block(tmp_path: Path) -> None:
    _write_outgoing(
        tmp_path,
        "### assignment → REQ@2.def.other\n\n```yaml\n- just\n- a\n- list\n```\n\nDescription.\n",
    )

    (finding,) = ConnectionMetadataScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("malformed-connection-metadata:")


def test_apply_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    _write_outgoing(
        tmp_path,
        "### assignment → REQ@2.def.other\n\n```yaml\nspecialization: [unterminated\n```\n\nDescription.\n",
    )
    view = _view(tmp_path)
    registry = StepRegistry()
    registry.register(ConnectionMetadataScanStep())

    report = apply_repository(
        view, FilesystemRepoUpgradeWriter(tmp_path), registry=registry, software_version="0.0.0-test"
    )

    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.touched_locations == frozenset()
