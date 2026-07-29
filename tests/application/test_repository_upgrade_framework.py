"""Framework tests for the `arch-repair upgrade` machinery: a fixture step exercising
detect/apply/idempotence through the real filesystem adapters, plus multi-repo aggregation."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.workspace import (
    RepoUpgradeTarget,
    apply_workspace,
    evaluate_workspace,
)
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)

_LEGACY = "legacy.txt"
_STEP_ID = "fixture-rename-marker"


class _FixtureStep:
    """Detects a legacy marker file and rewrites it to the new name — a stand-in for the real
    multiplicity-rename step, used here only to exercise the framework contract."""

    id = _STEP_ID
    version = 1
    description = "Rename legacy.txt to current.txt"
    scanned_surface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        content = view.read_text(_LEGACY)
        if content is None or view.read_text("current.txt") is not None:
            return []
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id="legacy-marker",
                location=_LEGACY,
                description="legacy.txt should be renamed to current.txt",
                severity="warning",
                auto_migratable=True,
                rewrite_summary="rename legacy.txt -> current.txt",
            )
        ]

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        content = view.read_text(_LEGACY)
        assert content is not None
        writer.write_text("current.txt", content)
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(_FixtureStep())
    return reg


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".arch-repo").mkdir(parents=True)
    root.joinpath(_LEGACY).write_text("hello", encoding="utf-8")
    return root


def test_evaluate_reports_finding_without_mutating(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    view = FilesystemRepoUpgradeView(root)
    report = evaluate_repository(view, registry=_registry(), software_version="0.0.0-test")

    assert report.unapplied_required_steps == (_STEP_ID,)
    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert not root.joinpath("current.txt").exists()
    assert root.joinpath(_LEGACY).exists()


def test_apply_rewrites_and_stamps_config(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    view = FilesystemRepoUpgradeView(root)
    writer = FilesystemRepoUpgradeWriter(root)

    report = apply_repository(view, writer, registry=_registry(), software_version="0.0.0-test")

    assert report.applied_steps_after == (_STEP_ID,)
    assert report.results[0].outcome == "applied"
    assert root.joinpath("current.txt").read_text(encoding="utf-8") == "hello"

    config = (root / ".arch-repo" / "config.yaml").read_text(encoding="utf-8")
    assert "format_contract_version" in config
    assert _STEP_ID in config


def test_apply_is_idempotent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    view = FilesystemRepoUpgradeView(root)
    writer = FilesystemRepoUpgradeWriter(root)
    registry = _registry()

    first = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")
    second = apply_repository(view, writer, registry=registry, software_version="0.0.0-test")

    assert first.applied_steps_after == (_STEP_ID,)
    assert second.applied_steps_before == (_STEP_ID,)
    assert second.results == ()
    assert second.unapplied_required_steps == ()


def test_apply_is_a_true_no_op_when_already_up_to_date(tmp_path: Path) -> None:
    """Not just idempotent in outcome — a fully up-to-date repo must see zero writes, so
    `--commit` is safe to run unconditionally (e.g. before every container start)."""
    root = _repo(tmp_path)
    view = FilesystemRepoUpgradeView(root)
    real_writer = FilesystemRepoUpgradeWriter(root)
    registry = _registry()

    apply_repository(view, real_writer, registry=registry, software_version="0.0.0-test")
    config_mtime = (root / ".arch-repo" / "config.yaml").stat().st_mtime_ns

    calls: list[str] = []

    class _SpyWriter:
        def write_text(self, relative_path: str, content: str) -> None:
            calls.append("write_text")
            real_writer.write_text(relative_path, content)

        def rebuild_index(self) -> None:
            calls.append("rebuild_index")
            real_writer.rebuild_index()

        def stamp_applied_steps(self, step_ids: frozenset[str], *, format_contract_version: str) -> None:
            calls.append("stamp_applied_steps")
            real_writer.stamp_applied_steps(step_ids, format_contract_version=format_contract_version)

    apply_repository(view, _SpyWriter(), registry=registry, software_version="0.0.0-test")

    assert calls == []
    assert (root / ".arch-repo" / "config.yaml").stat().st_mtime_ns == config_mtime


def test_workspace_aggregates_and_stamps_both_repos(tmp_path: Path) -> None:
    engagement = _repo(tmp_path / "engagement")
    enterprise = _repo(tmp_path / "enterprise")
    registry = _registry()
    targets = [
        RepoUpgradeTarget(FilesystemRepoUpgradeView(r), FilesystemRepoUpgradeWriter(r))
        for r in (engagement, enterprise)
    ]

    evaluated = evaluate_workspace(targets, registry=registry, software_version="0.0.0-test")
    assert len(evaluated.per_repo) == 2
    assert all(r.unapplied_required_steps == (_STEP_ID,) for r in evaluated.per_repo)

    applied = apply_workspace(targets, registry=registry, software_version="0.0.0-test")
    assert all(r.applied_steps_after == (_STEP_ID,) for r in applied.per_repo)
    assert engagement.joinpath("current.txt").exists()
    assert enterprise.joinpath("current.txt").exists()
    assert not applied.has_errors


def test_finding_validation_requires_rewrite_or_manual_instructions() -> None:
    import pytest

    with pytest.raises(ValueError, match="rewrite_summary"):
        UpgradeFinding(
            step_id="x",
            finding_id="y",
            location="z",
            description="d",
            severity="error",
            auto_migratable=True,
        )
    with pytest.raises(ValueError, match="manual_instructions"):
        UpgradeFinding(
            step_id="x",
            finding_id="y",
            location="z",
            description="d",
            severity="error",
            auto_migratable=False,
        )
