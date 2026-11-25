"""`arch-init --initialize-*-repo-if-empty` publishes a repository with nothing left to commit, and a
missing `local:` repository is refused with the way to start a new one.

The scaffold was committed and pushed first and the generated diagram includes
(`diagram-catalog/_archimate-*.puml`) written afterwards, so both new repositories started with
untracked files — the enterprise one kept them until someone committed there.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.workspace import workspace_init


def _bare(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


def test_both_initialized_repositories_are_clean_and_carry_their_includes(tmp_path: Path) -> None:
    engagement, enterprise = _bare(tmp_path / "engagement.git"), _bare(tmp_path / "enterprise.git")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = workspace / "arch-workspace.yaml"
    config.write_text(
        "engagement:\n"
        f"  git: {{url: {engagement}, branch: main, path: .arch/repos/engagement}}\n"
        "enterprise:\n"
        f"  git: {{url: {enterprise}, branch: main, path: .arch/repos/enterprise}}\n",
        encoding="utf-8",
    )

    workspace_init.main([
        "--config", str(config),
        "--initialize-engagement-repo-if-empty", "--initialize-enterprise-repo-if-empty",
    ])

    for name in ("engagement", "enterprise"):
        clone = workspace / ".arch" / "repos" / name
        status = subprocess.run(
            ["git", "status", "--porcelain", "-u"], cwd=clone, capture_output=True, text=True, check=True,
        ).stdout
        assert status == "", f"{name}: {status}"
        tracked = subprocess.run(
            ["git", "ls-files", "diagram-catalog"], cwd=clone, capture_output=True, text=True, check=True,
        ).stdout.split()
        assert "diagram-catalog/_archimate-stereotypes.puml" in tracked


def test_a_missing_local_repository_says_how_to_start_a_new_one(tmp_path: Path) -> None:
    config = tmp_path / "arch-workspace.yaml"
    config.write_text("engagement:\n  local: missing\nenterprise:\n  local: also-missing\n", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        workspace_init.main(["--config", str(config)])

    message = str(raised.value)
    assert "does not exist" in message
    assert "--initialize-engagement-repo-if-empty" in message and "git:" in message
