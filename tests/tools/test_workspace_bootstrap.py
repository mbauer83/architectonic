"""Regression tests for remote-aware workspace bootstrap (clone vs. local init).

These exercise ``_resolve_repo`` against *real* local git remotes so they pin the
exact defect that left a clean deployment showing an empty scaffold: with the
``initialize_if_empty`` flag on, a populated remote must be CLONED (sharing its
history and upstream), never re-initialized as an unrelated local repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.workspace.workspace_init import _resolve_repo

_AUTHOR = ("-c", "user.name=Seed", "-c", "user.email=seed@local.invalid")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _rev(cwd: Path, ref: str = "HEAD") -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=cwd, capture_output=True, text=True
    ).stdout.strip()


def _upstream(cwd: Path) -> tuple[int, str]:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout.strip()


def _bare_remote(tmp_path: Path, name: str = "remote.git") -> Path:
    remote = tmp_path / name
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True, text=True
    )
    return remote


def _populate(remote: Path, tmp_path: Path, message: str = "seed remote content") -> None:
    work = tmp_path / f"{remote.name}-seed"
    if not work.exists():
        subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True, text=True)
        _git(work, "remote", "add", "origin", str(remote))
    (work / "model").mkdir(exist_ok=True)
    (work / "model" / ".keep").write_text("x", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, *_AUTHOR, "commit", "-m", message)
    _git(work, "push", "origin", "main")


def _spec(remote: Path) -> dict:
    return {"git": {"url": str(remote), "branch": "main", "path": "repo"}}


def test_populated_remote_is_cloned_not_initialized(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    _populate(remote, tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()

    dest = _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)

    # Shares the remote's history (not a fresh local scaffold) ...
    assert _rev(dest) == _rev(remote, "main")
    assert "seed remote content" in _git(dest, "log", "--oneline").stdout
    # ... and has upstream tracking, so the watcher can fast-forward.
    rc, ref = _upstream(dest)
    assert rc == 0 and ref == "origin/main"


def test_empty_remote_is_initialized_and_published(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()

    dest = _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)

    assert (dest / "model").is_dir()
    has_commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=dest, capture_output=True, text=True
    )
    assert has_commit.returncode == 0  # a commit exists locally
    # The scaffold was published, establishing the branch and upstream tracking.
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", str(remote), "main"], capture_output=True, text=True
    ).stdout
    assert "refs/heads/main" in ls
    rc, ref = _upstream(dest)
    assert rc == 0 and ref == "origin/main"


def test_empty_remote_without_flag_raises(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(SystemExit, match="is empty"):
        _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=False)


def test_populated_remote_without_configured_branch_raises(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    _populate(remote, tmp_path)
    # Move the only branch to 'master'; 'main' no longer exists on the remote.
    _git(remote, "branch", "-m", "main", "master")
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(SystemExit, match="no branch 'main'"):
        _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)


def test_unreachable_remote_aborts_rather_than_guessing_empty(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    spec = {"git": {"url": str(tmp_path / "does-not-exist.git"), "branch": "main", "path": "repo"}}

    with pytest.raises(SystemExit, match="could not reach git remote"):
        _resolve_repo("enterprise", spec, ws, initialize_if_empty=True)


def test_existing_checkout_with_unrelated_history_aborts(tmp_path: Path) -> None:
    """Reproduces the production incident: a locally-initialized checkout is refused, loudly."""
    remote = _bare_remote(tmp_path)
    _populate(remote, tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    dest = ws / "repo"
    # A checkout with its OWN unrelated history that merely names the remote as origin.
    subprocess.run(["git", "init", "-b", "main", str(dest)], check=True, capture_output=True, text=True)
    (dest / "model").mkdir()
    (dest / "model" / ".keep").write_text("local", encoding="utf-8")
    _git(dest, "add", "-A")
    _git(dest, *_AUTHOR, "commit", "-m", "unrelated local scaffold")
    _git(dest, "remote", "add", "origin", str(remote))

    with pytest.raises(SystemExit, match="shares no history"):
        _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)


def test_existing_checkout_with_wrong_origin_aborts(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    _populate(remote, tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    dest = ws / "repo"
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True, capture_output=True, text=True)

    other = {"git": {"url": str(tmp_path / "somewhere-else.git"), "branch": "main", "path": "repo"}}
    with pytest.raises(SystemExit, match="expected"):
        _resolve_repo("enterprise", other, ws, initialize_if_empty=True)


def test_existing_checkout_missing_upstream_is_repaired(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    _populate(remote, tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    dest = ws / "repo"
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True, capture_output=True, text=True)
    _git(dest, "branch", "--unset-upstream")
    assert _upstream(dest)[0] != 0  # upstream really is gone

    _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)

    rc, ref = _upstream(dest)
    assert rc == 0 and ref == "origin/main"


def test_empty_checkout_adopts_remote_after_it_gains_commits(tmp_path: Path) -> None:
    remote = _bare_remote(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    dest = ws / "repo"
    # A prior clone of the then-empty remote leaves a commit-less checkout.
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True, capture_output=True, text=True)

    _populate(remote, tmp_path)  # remote gains real content afterwards

    resolved = _resolve_repo("enterprise", _spec(remote), ws, initialize_if_empty=True)

    assert resolved == dest.resolve()
    assert _rev(dest) == _rev(remote, "main")  # adopted remote history, no unrelated scaffold commit
    rc, ref = _upstream(dest)
    assert rc == 0 and ref == "origin/main"
