"""Real-git regression: stage_and_validate must not reject legitimate model content.

Reproduces the production failure where the whole engagement model was uncommitted
and `git diff --cached --check` tripped on Markdown whitespace / `===` setext
underlines (which it mistakes for conflict markers). The adapter must stage such a
tree without error.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.infrastructure.git.repair_adapter import GitRepairAdapter


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "engagement"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    return repo


def test_stage_and_validate_accepts_whitespace_and_setext_markdown(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    # Content that `git diff --cached --check` rejects: trailing whitespace, a blank line
    # at EOF, and a `=======` setext underline that --check reads as a conflict marker.
    doc = repo / "model" / "common" / "process" / "PRC@1.aaaaaa.x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Heading   \nUnderlined title\n=======\n\nbody with trailing space \n\n",
        encoding="utf-8",
    )

    adapter = GitRepairAdapter(repo, os.environ.copy())
    adapter.stage_and_validate()  # must not raise

    assert adapter.has_staged_changes()
    assert "PRC@1.aaaaaa.x.md" in _git(repo, "diff", "--cached", "--name-only")


def test_stage_and_validate_stages_untracked_whole_tree(tmp_path: Path) -> None:
    """An all-uncommitted tree (no baseline commit) stages cleanly and is committable."""
    repo = _init_repo(tmp_path)
    for rel in ("model/a/E@1.aa.x.md", "diagram-catalog/d/ARC@2.bb.y.puml"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("trailing space \n=======\n", encoding="utf-8")

    adapter = GitRepairAdapter(repo, os.environ.copy())
    adapter.stage_and_validate()

    staged = _git(repo, "diff", "--cached", "--name-only").splitlines()
    assert "model/a/E@1.aa.x.md" in staged
    assert "diagram-catalog/d/ARC@2.bb.y.puml" in staged


def test_stage_does_not_commit_m4_transaction_journal(tmp_path: Path) -> None:
    """An interrupted write's .arch-repo/transactions/ journal must never be staged."""
    repo = _init_repo(tmp_path)
    model = repo / "model" / "a" / "E@1.aa.x.md"
    model.parent.mkdir(parents=True)
    model.write_text("ok\n", encoding="utf-8")
    txn = repo / ".arch-repo" / "transactions" / "tx-123"
    txn.mkdir(parents=True)
    (txn / "intent").write_text('{"entries": []}\n', encoding="utf-8")
    (txn / "done").write_text("done\n", encoding="utf-8")

    GitRepairAdapter(repo, os.environ.copy()).stage_and_validate()

    staged = _git(repo, "diff", "--cached", "--name-only").splitlines()
    assert "model/a/E@1.aa.x.md" in staged
    assert not any(path.startswith(".arch-repo/transactions") for path in staged)
