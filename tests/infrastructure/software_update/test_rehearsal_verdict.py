"""The rehearsal reads a real dry-run report, so the two cannot drift on what blocks a commit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.cli.arch_repair_upgrade import main_upgrade
from src.infrastructure.software_update.rehearsal import RehearsalFailed, verdict_from_report
from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults


def _real_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict:
    root = tmp_path / "engagements" / "ENG-R" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)
    assert main_upgrade(["--repo-root", str(root), "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_a_current_repository_rehearses_clear(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    verdict = verdict_from_report(_real_report(tmp_path, capsys))

    assert verdict.repositories == 1 and verdict.clear


def test_blocking_uninspectable_and_erroring_findings_are_each_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    report = _real_report(tmp_path, capsys)
    report["repos"][0]["findings"] = [
        {"finding_id": "selection-divergent", "auto_migratable": False, "blocks_commit": True, "outcome": "skipped"},
        {"finding_id": "rename", "auto_migratable": True, "blocks_commit": False, "outcome": "skipped"},
    ]
    report["operational_targets"] = [
        {"kind": "assurance_sqlcipher", "state": "uninspectable", "findings": []},
        {"kind": "guidance_cache", "state": "pending", "findings": [
            {"finding_id": "cache-format", "auto_migratable": True, "blocks_commit": False, "outcome": "error"},
        ]},
    ]

    verdict = verdict_from_report(report)

    assert not verdict.clear
    assert verdict.blocking and "selection-divergent" in verdict.blocking[0]
    assert verdict.uninspectable == ("assurance_sqlcipher",)
    assert verdict.errors and "cache-format" in verdict.errors[0]
    assert verdict.auto_migratable == 2 and verdict.operational_targets == 2


def test_a_report_schema_this_version_does_not_read_is_refused() -> None:
    with pytest.raises(RehearsalFailed, match="schema"):
        verdict_from_report({"report_schema_version": "99", "repos": []})


def test_a_checkout_tool_runs_without_relocking_or_resyncing_the_project(tmp_path: Path) -> None:
    from src.infrastructure.software_update._commands import checkout_tool

    command = checkout_tool("uv", tmp_path, "arch-repair", "upgrade", "--json")

    # Otherwise `uv run` rewrites uv.lock after the version bump (a dirty checkout) and syncs the
    # default groups, dropping the ones the derived selection installed. Both happened in a live drive.
    assert command[:4] == ["uv", "run", "--frozen", "--no-sync"]
    assert command[4:] == ["--project", str(tmp_path), "arch-repair", "upgrade", "--json"]
