"""`arch-repair upgrade --commit` leaves a safety point, and `--restore` returns to it byte for byte.

The upgrade guide used to hand the operator a table of things to back up first. The command now takes
the safety point itself, after the backend-not-serving gate and before its first write: every repository
pinned under a git ref, every operational target copied beside the set's record. Asserted through the
CLI, over a real git repository with an uncommitted edit and an untracked file, with a commit made to
fail after it has written — the situation `--restore` exists for.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.application.deployment_upgrade.ports import OperationalStepRegistry
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import StepRegistry
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.cli import arch_repair_upgrade as cli


class _RenameStep:
    id = "fixture-rename"
    version = 1
    description = "fixture"
    scanned_surface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        if view.read_text("legacy.txt") is None or view.read_text("current.txt") is not None:
            return []
        return [UpgradeFinding(
            step_id=self.id, finding_id="legacy-marker", location="legacy.txt",
            description="rename legacy.txt", severity="warning", auto_migratable=True,
            rewrite_summary="legacy.txt -> current.txt",
        )]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        writer.write_text("current.txt", view.read_text("legacy.txt") or "")
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _registry() -> StepRegistry:
    registry = StepRegistry()
    registry.register(_RenameStep())
    return registry


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "legacy.txt").write_text("hello", encoding="utf-8")
    (path / "notes.md").write_text("committed notes\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    # The state an actively used repository is in: an edit not yet committed, a file not yet added.
    (path / "notes.md").write_text("edited, not committed\n", encoding="utf-8")
    (path / "draft.md").write_text("never added\n", encoding="utf-8")
    return path


def _tree(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): p.read_text(encoding="utf-8")
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.parts and ".arch-repo" not in p.parts
    }


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


def test_a_commit_that_fails_after_writing_is_taken_back_by_restore(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(tmp_path / "repo")
    before = _tree(repo)
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout

    real_apply = cli.apply_workspace

    def apply_then_die(*args, **kwargs):  # type: ignore[no-untyped-def]
        real_apply(*args, **kwargs)
        assert (repo / "current.txt").exists(), "the step must have written before the failure"
        raise RuntimeError("simulated failure after the first repository applied")

    monkeypatch.setattr(cli, "apply_workspace", apply_then_die)
    with pytest.raises(RuntimeError, match="simulated failure"):
        cli.main_upgrade(
            ["--repo-root", str(repo), "--commit"],
            registry=_registry(), operational_registry=OperationalStepRegistry(),
        )
    assert _tree(repo) != before, "the failure left the repository written, which is the case under test"

    code = cli.main_upgrade(
        ["--repo-root", str(repo), "--list-checkpoints", "--json"],
        registry=_registry(), operational_registry=OperationalStepRegistry(),
    )
    assert code == 0
    sets = json.loads(capsys.readouterr().out)
    assert len(sets) == 1
    assert [Path(r["root"]) for r in sets[0]["repositories"]] == [repo]

    code = cli.main_upgrade(
        ["--repo-root", str(repo), "--restore", sets[0]["id"]],
        registry=_registry(), operational_registry=OperationalStepRegistry(),
    )

    assert code == 0
    assert _tree(repo) == before
    status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert status_after == status_before
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True)
    assert branch.stdout.strip() == "main"


def test_a_successful_commit_reports_its_set_and_keeps_only_one(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(tmp_path / "repo")
    code = cli.main_upgrade(
        ["--repo-root", str(repo), "--commit", "--json"],
        registry=_registry(), operational_registry=OperationalStepRegistry(),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_schema_version"] == "2"
    first = payload["checkpoint_set"]
    assert first is not None and first["repositories"][0]["ref"].startswith("refs/arch-repair/pre-upgrade/")

    # A second run has nothing to write, so it takes no set and prunes nothing: still exactly one.
    code = cli.main_upgrade(
        ["--repo-root", str(repo), "--commit", "--json"],
        registry=_registry(), operational_registry=OperationalStepRegistry(),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoint_set"] is None
    cli.main_upgrade(
        ["--repo-root", str(repo), "--list-checkpoints", "--json"],
        registry=_registry(), operational_registry=OperationalStepRegistry(),
    )
    assert [s["id"] for s in json.loads(capsys.readouterr().out)] == [first["id"]]


def test_a_dry_run_takes_no_checkpoint(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(tmp_path / "repo")
    code = cli.main_upgrade(
        ["--repo-root", str(repo), "--json"], registry=_registry(), operational_registry=OperationalStepRegistry(),
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["checkpoint_set"] is None
    assert not (tmp_path / ".arch").exists()
