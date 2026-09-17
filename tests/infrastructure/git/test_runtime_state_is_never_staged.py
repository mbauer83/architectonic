"""The one staging rule stages the work and never `.arch/`, whether or not the repository ignores it.

A repository whose own `.gitignore` lists `.arch/` — the enterprise template does — and whose
`.arch/` exists made git refuse the previous pathspec outright, so a data upgrade's checkpoint
failed on the first real deployment it met. Both configurations are the round trip here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git._git_command import STAGE_ALL_BUT_RUNTIME_STATE, run_repo_git


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.org", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture(params=["ignored", "untracked"])
def repo(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".gitignore").write_text(".arch/\n" if request.param == "ignored" else "")
    (tmp_path / "model.yaml").write_text("a: 1\n")
    _git(tmp_path, "add", "-A", ".")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / ".arch").mkdir()
    (tmp_path / ".arch" / "backend.pid").write_text("4242")
    (tmp_path / "model.yaml").write_text("a: 2\n")
    (tmp_path / "new.yaml").write_text("b: 1\n")
    return tmp_path


def test_the_work_is_staged_and_runtime_state_is_not(repo: Path) -> None:
    rc, _, stderr = run_repo_git(repo, *STAGE_ALL_BUT_RUNTIME_STATE)

    assert rc == 0, stderr
    staged = set(_git(repo, "diff", "--cached", "--name-only").split())
    assert {"model.yaml", "new.yaml"} <= staged
    assert not any(name.startswith(".arch/") for name in staged)
