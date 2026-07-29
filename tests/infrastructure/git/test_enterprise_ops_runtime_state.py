"""Runtime sync state (`.arch/`) must never be staged, committed, or counted as work.

Reproduces the production leak where `git add .` in the save path committed
.arch/enterprise-sync.json onto the working branch and it rode a PR into
origin/main — carrying a stale "accumulating" state to every future clone.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.git.enterprise_git_ops import commit_enterprise_work, has_uncommitted_changes


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "enterprise"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _write_state(repo: Path) -> None:
    state = repo / ".arch" / "enterprise-sync.json"
    state.parent.mkdir(exist_ok=True)
    state.write_text('{"status": "accumulating"}\n', encoding="utf-8")


def test_save_commits_work_but_never_the_state_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_state(repo)
    doc = repo / "model" / "motivation" / "requirement" / "REQ@1.Abc123.thing.md"
    doc.parent.mkdir(parents=True)
    # Save commits verify the working tree, so the fixture must be a valid artifact.
    doc.write_text(
        "---\n"
        "artifact-id: REQ@1.Abc123.thing\n"
        "artifact-type: requirement\n"
        "name: Thing\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        "<!-- §content -->\n\n"
        "## Thing\n\n"
        "Fixture requirement.\n\n"
        "## Properties\n\n"
        "| Attribute | Value |\n"
        "|---|---|\n"
        "| (none) | (none) |\n\n"
        "<!-- §display -->\n\n"
        "### archimate\n\n"
        "```yaml\n"
        "label: Thing\n"
        "alias: REQ_Abc123\n"
        "```\n",
        encoding="utf-8",
    )

    commit_enterprise_work(repo, "save work")

    tracked = _git(repo, "ls-files")
    assert "REQ@1.Abc123.thing.md" in tracked
    assert ".arch/enterprise-sync.json" not in tracked


def test_state_file_alone_is_not_unsaved_work(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_state(repo)
    assert not has_uncommitted_changes(repo)

    (repo / "model").mkdir()
    (repo / "model" / "real-work.md").write_text("x\n", encoding="utf-8")
    assert has_uncommitted_changes(repo)


def test_pathspec_filtered_check_still_excludes_state(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_state(repo)
    assert not has_uncommitted_changes(repo, ".arch")
