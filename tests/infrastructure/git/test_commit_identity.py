from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.infrastructure.git.git_work_commits import commit_engagement_work


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo_without_git_config(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_NAME", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    (repo / "change.md").write_text("change", encoding="utf-8")
    return repo


def test_commit_succeeds_without_git_config_using_service_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _repo_without_git_config(tmp_path, monkeypatch)
    monkeypatch.delenv("ARCH_GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("ARCH_GIT_AUTHOR_EMAIL", raising=False)

    commit_engagement_work(repo, "save")

    assert _git(repo, "show", "-s", "--format=%an|%ae|%cn|%ce") == (
        "Architecture Repository Service|arch-service@localhost|"
        "Architecture Repository Service|arch-service@localhost"
    )


def test_the_process_environment_does_not_author_the_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A `GIT_AUTHOR_*` in the server's environment does not displace the configured identity."""
    repo = _repo_without_git_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ARCH_GIT_AUTHOR_NAME", "Arch Service")
    monkeypatch.setenv("ARCH_GIT_AUTHOR_EMAIL", "service@example.invalid")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Someone Else")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "someone@example.invalid")

    commit_engagement_work(repo, "save")

    assert _git(repo, "show", "-s", "--format=%an|%ae|%cn|%ce") == (
        "Arch Service|service@example.invalid|Arch Service|service@example.invalid"
    )


def test_commit_does_not_mutate_process_identity_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _repo_without_git_config(tmp_path, monkeypatch)
    before = dict(os.environ)

    commit_engagement_work(repo, "save")

    assert os.environ == before
