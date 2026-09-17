"""A checkpoint set that cannot be completed leaves no ref, no directory and every branch where it was.

The first live data upgrade over two repositories failed while pinning the second, and left the
first repository carrying a `refs/arch-repair/pre-upgrade/<id>` that no record named — a snapshot
`--list-checkpoints` could not show and `--restore` could not reach. The set is taken whole or not at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.cli import _upgrade_checkpoints as checkpoints


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.org", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "model.yaml").write_text("a: 1\n")
    _git(path, "add", "-A", ".")
    _git(path, "commit", "-qm", "init")
    (path / "model.yaml").write_text("a: 2\n")  # dirty, so a transient checkpoint commit is made
    return path


def test_a_failure_on_the_second_repository_releases_the_first_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _repo(tmp_path / "first"), _repo(tmp_path / "second")
    head_before = _git(first, "rev-parse", "HEAD")
    real_pin = checkpoints.pin_checkpoint

    def failing_second(repo: Path, transient, name):  # noqa: ANN001, ANN202
        if repo == second:
            raise RuntimeError("update-ref refused")
        return real_pin(repo, transient, name)

    monkeypatch.setattr(checkpoints, "pin_checkpoint", failing_second)
    base = tmp_path / ".arch" / "upgrade-checkpoints"

    with pytest.raises(checkpoints.CheckpointFailed, match="nothing was written"):
        checkpoints.take_checkpoint_set([first, second], [], base)

    assert _git(first, "for-each-ref", "refs/arch-repair") == ""
    assert _git(second, "for-each-ref", "refs/arch-repair") == ""
    assert not base.exists() or not any(base.iterdir())
    for repo in (first, second):
        assert _git(repo, "rev-parse", "HEAD") == (head_before if repo == first else _git(repo, "rev-parse", "HEAD"))
        assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert (repo / "model.yaml").read_text() == "a: 2\n", "the operator's dirty edit is still there"
        assert _git(repo, "log", "--oneline").count("\n") == 0, "no transient checkpoint commit stayed"


def test_a_completed_set_pins_every_repository_and_records_the_set(tmp_path: Path) -> None:
    first, second = _repo(tmp_path / "first"), _repo(tmp_path / "second")
    base = tmp_path / ".arch" / "upgrade-checkpoints"

    taken = checkpoints.take_checkpoint_set([first, second], [], base)

    assert {r.root for r in taken.repositories} == {str(first), str(second)}
    assert (base / taken.id / "checkpoint-set.json").is_file()
    assert _git(first, "for-each-ref", "refs/arch-repair") and _git(second, "for-each-ref", "refs/arch-repair")
