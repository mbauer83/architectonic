"""`arch-repair upgrade` CLI tests: dry-run/commit, guards, --json contract, workspace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import StepRegistry
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.cli import arch_repair_upgrade as cli


class _FixtureStep:
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


def _registry() -> StepRegistry:
    reg = StepRegistry()
    reg.register(_FixtureStep())
    return reg


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "legacy.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch):
    """Every test here runs with an assumed-stopped backend unless explicitly overridden."""
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


def test_human_output_includes_coverage_disclaimer(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    cli.main_upgrade(["--repo-root", str(repo)], registry=_registry())

    out = capsys.readouterr().out
    assert "does not certify the repo is fully current" in out


def test_dry_run_never_mutates(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    exit_code = cli.main_upgrade(["--repo-root", str(repo)], registry=_registry())

    assert exit_code == 0
    assert not (repo / "current.txt").exists()
    assert "legacy-marker" in capsys.readouterr().out


def test_commit_applies_and_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    first = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())
    assert first == 0
    assert (repo / "current.txt").read_text(encoding="utf-8") == "hello"

    # Re-running against the same, now-clean (user has committed the rewrite) worktree must be
    # a no-op: idempotence is what makes it safe to re-run `upgrade` on any user repository.
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "apply upgrade"], cwd=repo, check=True)

    second = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())
    assert second == 0


def test_commit_resumes_cleanly_after_a_simulated_crash(tmp_path: Path, monkeypatch) -> None:
    """A process kill mid-write leaves only a stray temp file + a stale/absent stamp — both
    must be self-healing on the next --commit, with no double-application and no data loss."""
    repo = tmp_path / "repo"
    _init_repo(repo)

    orphan = repo / ".current.txt.tmp-99999"
    orphan.write_text("half-written-before-the-crash", encoding="utf-8")

    exit_code = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())

    assert exit_code == 0
    assert not orphan.exists()
    assert (repo / "current.txt").read_text(encoding="utf-8") == "hello"


def test_commit_does_not_block_on_unrelated_uncommitted_work(tmp_path: Path) -> None:
    """An actively-used architecture repo has uncommitted model edits most of the time (via
    MCP tools) — that is normal operating state, not a reason to refuse --commit, as long as
    none of the run's own target files are among them."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "uncommitted.txt").write_text("x", encoding="utf-8")

    exit_code = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())

    assert exit_code == 0
    assert (repo / "current.txt").exists()
    assert (repo / "uncommitted.txt").exists()  # untouched, never staged or reverted


def test_commit_proceeds_and_carries_forward_an_uncommitted_edit_to_a_touched_file(
    tmp_path: Path, capsys
) -> None:
    """Git status is not a safety gate: a step reads whatever is on disk right now, so an
    uncommitted local edit to the exact file a step targets is carried into the rewrite, not
    lost — this must never block, only surface an informational note."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "legacy.txt").write_text("hello-edited-locally", encoding="utf-8")

    exit_code = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())

    assert exit_code == 0
    assert (repo / "current.txt").read_text(encoding="utf-8") == "hello-edited-locally"
    assert "legacy.txt" in capsys.readouterr().out


def test_commit_refuses_when_backend_serves_target_repo(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "probe_backend_identity", lambda *_a, **_k: _identity_for(repo))

    with pytest.raises(SystemExit, match="is serving"):
        cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())

    assert not (repo / "current.txt").exists()


def test_commit_fails_closed_when_backend_responds_without_identity_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "probe_backend_identity", lambda *_a, **_k: None)

    with pytest.raises(SystemExit, match="backend-identity"):
        cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())


def test_commit_does_not_block_on_unrelated_backend(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    other = tmp_path / "unrelated"
    other.mkdir()
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "probe_backend_identity", lambda *_a, **_k: _identity_for(other))

    exit_code = cli.main_upgrade(["--repo-root", str(repo), "--commit"], registry=_registry())

    assert exit_code == 0
    assert (repo / "current.txt").exists()


def test_json_output_schema(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    cli.main_upgrade(["--repo-root", str(repo), "--json"], registry=_registry())

    payload = json.loads(capsys.readouterr().out)
    (repo_report,) = payload["repos"]
    assert repo_report["repo_root"] == str(repo)
    assert repo_report["coverage_note"]  # "clean report" != "fully current"
    assert "software_version" in repo_report
    assert "format_contract_version" in repo_report
    assert repo_report["available_steps"] == [{"id": "fixture-step", "version": 1}]
    assert repo_report["applied_steps_before"] == []
    assert repo_report["applied_steps_after"] == []
    assert repo_report["unapplied_required_steps"] == ["fixture-step"]
    (finding,) = repo_report["findings"]
    assert finding["step_id"] == "fixture-step"
    assert finding["outcome"] == "skipped"


def test_workspace_multi_repo_stamps_both_and_aggregates(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    engagement = workspace / "engagements" / "ENG" / "architecture-repository"
    enterprise = workspace / "enterprise-repository"
    _init_repo(engagement)
    _init_repo(enterprise)

    exit_code = cli.main_upgrade(
        ["--repo-root", str(engagement), "--repo-root", str(enterprise), "--commit"],
        registry=_registry(),
    )

    assert exit_code == 0
    assert (engagement / "current.txt").exists()
    assert (enterprise / "current.txt").exists()
    assert "format_contract_version" in (engagement / ".arch-repo" / "config.yaml").read_text()
    assert "format_contract_version" in (enterprise / ".arch-repo" / "config.yaml").read_text()


def _identity_for(repo_root: Path):
    from src.infrastructure.repository_upgrade.guard import BackendIdentity

    return BackendIdentity(repo_roots=(str(repo_root.resolve()),), software_version="9.9.9")
