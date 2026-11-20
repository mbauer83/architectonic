"""The one staging rule stages the work and never runtime state, whether or not the repository ignores it.

A repository whose own `.gitignore` lists `.arch/` — the enterprise template does — and whose
`.arch/` exists made git refuse the previous pathspec outright, so a data upgrade's checkpoint
failed on the first real deployment it met. The same refusal waits for any exclude that begins with
literal text naming an ignored path, which is every piece of runtime state under `.arch-repo/` once
its `.gitignore` is in place. Both configurations are the round trip here, for every declared entry.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.domain.repository.repo_layout import RUNTIME_STATE
from src.infrastructure.git._git_command import STAGE_ALL_BUT_RUNTIME_STATE, run_repo_git
from src.infrastructure.git.git_repository_state import has_uncommitted_changes
from src.infrastructure.runtime_state_ignore import RUNTIME_STATE_IGNORE_LINES, ensure_runtime_state_ignored
from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.org", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def _a_file_of(runtime_state: str) -> str:
    """A file that is, or is inside, one declared piece of runtime state."""
    return f"{runtime_state}held/state.json" if runtime_state.endswith("/") else runtime_state


_RUNTIME_FILES = [_a_file_of(path) for path in RUNTIME_STATE]


def _produce_runtime_state(repo: Path) -> None:
    for relative in _RUNTIME_FILES:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")


@pytest.fixture(params=["ignored", "untracked"])
def repo(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".gitignore").write_text(".arch/\n" if request.param == "ignored" else "")
    if request.param == "ignored":
        ensure_runtime_state_ignored(tmp_path)
    (tmp_path / "model.yaml").write_text("a: 1\n")
    _git(tmp_path, "add", "-A", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_the_work_is_staged_and_runtime_state_is_not(repo: Path) -> None:
    _produce_runtime_state(repo)
    (repo / "model.yaml").write_text("a: 2\n")
    (repo / "new.yaml").write_text("b: 1\n")

    rc, _, stderr = run_repo_git(repo, *STAGE_ALL_BUT_RUNTIME_STATE)

    assert rc == 0, stderr
    staged = set(_git(repo, "diff", "--cached", "--name-only").split())
    assert {"model.yaml", "new.yaml"} <= staged
    assert staged.isdisjoint(_RUNTIME_FILES)


def test_runtime_state_alone_is_nothing_to_save(repo: Path) -> None:
    """The same definition read the other way: the question a save asks before it stages."""
    _produce_runtime_state(repo)

    assert has_uncommitted_changes(repo) is False

    (repo / "new.yaml").write_text("b: 1\n")

    assert has_uncommitted_changes(repo) is True


def test_a_repository_brought_up_to_defaults_ignores_its_runtime_state_from_the_first_commit(
    tmp_path: Path,
) -> None:
    """The `.gitignore` beside the configuration is content, so it is written with the configuration
    — not left for whichever operation first produces runtime state. A pull was that operation in a
    fresh clone, and left the file behind for the next save to commit under someone else's message.

    Raw `git add .` here, deliberately: the file is for a person in a clone, since the product's own
    commit paths exclude runtime state by pathspec and do not need it."""
    _git(tmp_path, "init", "-q", "-b", "main")
    ensure_arch_repo_defaults(tmp_path)
    assert (tmp_path / ".arch-repo" / ".gitignore").read_text().splitlines() == list(RUNTIME_STATE_IGNORE_LINES)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "scaffold")

    _produce_runtime_state(tmp_path)
    _git(tmp_path, "add", ".")

    staged = set(_git(tmp_path, "diff", "--cached", "--name-only").split())
    assert staged.isdisjoint(path for path in _RUNTIME_FILES if path.startswith(".arch-repo/"))


def test_the_ignore_file_keeps_a_line_someone_added(tmp_path: Path) -> None:
    gitignore = tmp_path / ".arch-repo" / ".gitignore"
    gitignore.parent.mkdir()
    gitignore.write_text("local-notes/\ntransactions/\n")

    assert ensure_runtime_state_ignored(tmp_path) is True
    assert ensure_runtime_state_ignored(tmp_path) is False

    lines = gitignore.read_text().splitlines()
    assert lines[:2] == ["local-notes/", "transactions/"]
    assert sorted(lines) == sorted({"local-notes/", *RUNTIME_STATE_IGNORE_LINES})
