"""Deployment-scoped `arch-repair upgrade`: operational targets, exit codes, JSON."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.application.deployment_upgrade.ports import (
    OperationalStepRegistry,
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import StepRegistry
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.cli import arch_repair_upgrade as cli


class _RepoFixtureStep:
    id = "fixture-step"
    version = 1
    description = "fixture"
    scanned_surface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        if view.read_text("legacy.txt") is None or view.read_text("current.txt") is not None:
            return []
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id="legacy-marker",
                location="legacy.txt",
                description="rename legacy.txt",
                severity="warning",
                auto_migratable=True,
                rewrite_summary="rename legacy.txt -> current.txt",
            )
        ]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding]
    ) -> list[AppliedFinding]:
        writer.write_text("current.txt", view.read_text("legacy.txt") or "")
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


class _CacheFixtureStep:
    """Migrates any cached guidance document whose format header is 1."""

    id = "cache-fixture-step"
    version = 2
    kind = "guidance_cache"
    description = "fixture cache migration"

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        findings = []
        for member in view.list_files("*.guidance.yaml"):
            content = view.read_text(member) or ""
            if "guidance_format: 1" in content:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"v1-header:{member}",
                        location=member,
                        description="cache header at format 1",
                        severity="warning",
                        auto_migratable=True,
                        rewrite_summary="bump header",
                    )
                )
        return findings

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        if self._fail:
            raise RuntimeError("simulated cache migration failure")
        for finding in findings:
            content = view.read_text(finding.location) or ""
            uow.write_text(finding.location, content.replace("guidance_format: 1", "guidance_format: 2"))
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _repo_registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(_RepoFixtureStep())
    return reg


def _op_registry(*steps) -> OperationalStepRegistry:  # type: ignore[no-untyped-def]
    reg = OperationalStepRegistry()
    for step in steps:
        reg.register(step)
    return reg


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "legacy.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _deployment(tmp_path: Path) -> Path:
    root = tmp_path / "deploy"
    (root / "guidance-cache").mkdir(parents=True)
    (root / "settings.yaml").write_text("{}\n", encoding="utf-8")
    (root / "guidance-cache" / "m.guidance.yaml").write_text(
        "guidance_format: 1\n", encoding="utf-8"
    )
    return root


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


class TestDryRun:
    def test_lists_operational_targets_and_exits_zero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        root = _deployment(tmp_path)
        code = cli.main_upgrade(
            ["--deployment-root", str(root), "--json"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep()),
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["report_schema_version"] == "1"
        kinds = {t["kind"]: t for t in payload["operational_targets"]}
        assert kinds["guidance_cache"]["state"] == "pending"
        assert kinds["deployment_settings"]["state"] == "current"
        preflight = payload["deployment_preflight"]
        assert preflight["operator_owned"]
        # Dry-run writes nothing:
        cache_doc = root / "guidance-cache" / "m.guidance.yaml"
        assert cache_doc.read_text(encoding="utf-8") == "guidance_format: 1\n"

    def test_workspace_only_invocations_never_reach_operational_targets(
        self, tmp_path: Path, capsys
    ) -> None:  # type: ignore[no-untyped-def]
        repo = tmp_path / "repo"
        _init_repo(repo)
        code = cli.main_upgrade(
            ["--repo-root", str(repo), "--json"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep()),
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["operational_targets"] == []
        assert payload["deployment_preflight"] is None


class TestCommit:
    def test_commit_applies_operational_migrations_atomically(self, tmp_path: Path) -> None:
        root = _deployment(tmp_path)
        code = cli.main_upgrade(
            ["--deployment-root", str(root), "--commit"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep()),
        )
        assert code == 0
        cache_doc = root / "guidance-cache" / "m.guidance.yaml"
        assert cache_doc.read_text(encoding="utf-8") == "guidance_format: 2\n"

    def test_commit_is_idempotent(self, tmp_path: Path) -> None:
        root = _deployment(tmp_path)
        args = ["--deployment-root", str(root), "--commit"]
        for _ in range(2):
            code = cli.main_upgrade(
                args,
                registry=_repo_registry(),
                operational_registry=_op_registry(_CacheFixtureStep()),
            )
            assert code == 0

    def test_later_target_failure_after_committed_repo_exits_partial_apply(
        self, tmp_path: Path, capsys
    ) -> None:  # type: ignore[no-untyped-def]
        root = _deployment(tmp_path)
        repo = tmp_path / "repo"
        _init_repo(repo)
        code = cli.main_upgrade(
            ["--repo-root", str(repo), "--deployment-root", str(root), "--commit", "--json"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep(fail=True)),
        )
        assert code == cli.EXIT_PARTIAL_APPLY
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] == "partial_apply"
        # The repository unit committed; the cache migration rolled back whole:
        assert (repo / "current.txt").exists()
        cache_doc = root / "guidance-cache" / "m.guidance.yaml"
        assert cache_doc.read_text(encoding="utf-8") == "guidance_format: 1\n"

    def test_failure_before_any_commit_exits_infrastructure_failure(
        self, tmp_path: Path
    ) -> None:
        root = _deployment(tmp_path)
        code = cli.main_upgrade(
            ["--deployment-root", str(root), "--commit"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep(fail=True)),
        )
        assert code == cli.EXIT_INFRASTRUCTURE_FAILURE

    def test_conflicting_explicit_selectors_error_before_any_target_opens(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        root = _deployment(tmp_path)
        monkeypatch.setenv("ARCH_ASSURANCE_DB_PATH", str(tmp_path / "env-store.db"))
        with pytest.raises(SystemExit) as excinfo:
            cli.main_upgrade(
                [
                    "--deployment-root",
                    str(root),
                    "--assurance-store",
                    str(tmp_path / "cli-store.db"),
                    "--commit",
                ],
                registry=_repo_registry(),
                operational_registry=_op_registry(),
            )
        assert "assurance_db_path" in str(excinfo.value)

    def test_exclude_target_skips_and_notes_uncertified_readiness(
        self, tmp_path: Path, capsys
    ) -> None:  # type: ignore[no-untyped-def]
        root = _deployment(tmp_path)
        code = cli.main_upgrade(
            ["--deployment-root", str(root), "--exclude-target", "guidance_cache", "--json"],
            registry=_repo_registry(),
            operational_registry=_op_registry(_CacheFixtureStep()),
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        kinds = [t["kind"] for t in payload["operational_targets"]]
        assert "guidance_cache" not in kinds
        notes = payload["deployment_preflight"]["notes"]
        assert any("NOT certified" in note for note in notes)
