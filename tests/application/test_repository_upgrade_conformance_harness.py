"""Proves the step-conformance harness itself actually catches the failure mode it
exists for: a well-behaved (narrow, in-place) step passes; a badly-behaved
(reconstruct-from-scratch) step — which would silently drop an uncommitted edit or unknown
field — fails it loudly."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from tests.support.repository_upgrade_conformance import assert_step_preserves_unknown_content

_FIXTURE = "---\nlegacy-key: true\nunknown-field: keep-me\n---\nbody\n"


class _WellBehavedStep:
    id = "well-behaved"
    version = 1
    description = "narrow in-place rewrite"
    scanned_surface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        content = view.read_text("fixture.md")
        if content is None or "legacy-key: true" not in content:
            return []
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id="legacy-key",
                location="fixture.md",
                description="rename legacy-key -> current-key",
                severity="warning",
                auto_migratable=True,
                rewrite_summary="rename legacy-key -> current-key",
            )
        ]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding]
    ) -> list[AppliedFinding]:
        content = view.read_text("fixture.md") or ""
        writer.write_text("fixture.md", content.replace("legacy-key: true", "current-key: true"))
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


class _BadlyBehavedStep(_WellBehavedStep):
    """Reconstructs the file from scratch instead of rewriting in place — the exact bug
    this harness exists to catch: anything the step doesn't explicitly know about (an
    uncommitted edit, an unrelated field) is silently dropped."""

    id = "badly-behaved"

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding]
    ) -> list[AppliedFinding]:
        writer.write_text("fixture.md", "---\ncurrent-key: true\n---\nbody\n")
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _view_and_writer(tmp_path: Path) -> tuple[FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter]:
    (tmp_path / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "fixture.md").write_text(_FIXTURE, encoding="utf-8")
    return FilesystemRepoUpgradeView(tmp_path), FilesystemRepoUpgradeWriter(tmp_path)


def test_well_behaved_step_passes_the_harness(tmp_path: Path) -> None:
    view, writer = _view_and_writer(tmp_path)

    assert_step_preserves_unknown_content(
        _WellBehavedStep(), view, writer, location="fixture.md", unknown_marker="unknown-field: keep-me"
    )


def test_badly_behaved_step_fails_the_harness(tmp_path: Path) -> None:
    view, writer = _view_and_writer(tmp_path)

    with pytest.raises(AssertionError, match="dropped unrelated content"):
        assert_step_preserves_unknown_content(
            _BadlyBehavedStep(), view, writer, location="fixture.md", unknown_marker="unknown-field: keep-me"
        )


def test_harness_rejects_bad_test_setup_when_marker_absent_before_apply(tmp_path: Path) -> None:
    (tmp_path / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "fixture.md").write_text("---\nlegacy-key: true\n---\nbody\n", encoding="utf-8")
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    with pytest.raises(AssertionError, match="test setup error"):
        assert_step_preserves_unknown_content(
            _WellBehavedStep(), view, writer, location="fixture.md", unknown_marker="unknown-field: keep-me"
        )


def test_harness_rejects_always_manual_steps(tmp_path: Path) -> None:
    view, writer = _view_and_writer(tmp_path)

    class _ManualOnlyStep(_WellBehavedStep):
        id = "manual-only"

        def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
            findings = super().detect(view)
            return [
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f.finding_id,
                    location=f.location,
                    description=f.description,
                    severity=f.severity,
                    auto_migratable=False,
                    manual_instructions="review by hand",
                )
                for f in findings
            ]

    with pytest.raises(AssertionError, match="only manual"):
        assert_step_preserves_unknown_content(
            _ManualOnlyStep(), view, writer, location="fixture.md", unknown_marker="unknown-field: keep-me"
        )
