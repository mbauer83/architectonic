"""Unit tests for git_remote decision logic (no subprocess): classification,
clone-vs-initialize, and fatal/race-safe publication."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.workspace import git_remote
from src.infrastructure.workspace.git_remote import BootstrapContext, RemoteState


def _ctx(tmp_path: Path, *, initialize_if_empty: bool) -> BootstrapContext:
    return BootstrapContext(
        label="enterprise",
        url="git@example.com:org/ent.git",
        branch="main",
        dest=tmp_path / "ent",
        initialize_if_empty=initialize_if_empty,
        env=None,
        author_name="arch-init",
        author_email="arch-init@local.invalid",
    )


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- classify_remote ---------------------------------------------------------


def test_classify_empty_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote, "run_git", lambda *a, **k: _Result(0, ""))
    assert git_remote.classify_remote("url", "main") is RemoteState.EMPTY


def test_classify_remote_with_configured_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote, "run_git", lambda *a, **k: _Result(0, "abc123\trefs/heads/main\n"))
    assert git_remote.classify_remote("url", "main") is RemoteState.HAS_BRANCH


def test_classify_remote_with_only_other_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        git_remote, "run_git", lambda *a, **k: _Result(0, "abc\trefs/heads/master\ndef\trefs/tags/v1\n")
    )
    assert git_remote.classify_remote("url", "main") is RemoteState.OTHER_REFS


def test_classify_remote_raises_on_inconclusive_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote, "run_git", lambda *a, **k: _Result(128, "", "connect failed"))
    with pytest.raises(SystemExit, match="could not reach git remote"):
        git_remote.classify_remote("url", "main")


# --- bootstrap_absent --------------------------------------------------------


def test_bootstrap_absent_clones_a_populated_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.HAS_BRANCH)
    cloned: list = []
    monkeypatch.setattr(git_remote, "clone", lambda url, branch, dest, env=None: cloned.append(url))
    monkeypatch.setattr(git_remote, "_initialize_and_publish", lambda ctx: pytest.fail("must not initialize"))

    git_remote.bootstrap_absent(_ctx(tmp_path, initialize_if_empty=True))
    assert cloned


def test_bootstrap_absent_rejects_remote_missing_the_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.OTHER_REFS)
    with pytest.raises(SystemExit, match="no branch 'main'"):
        git_remote.bootstrap_absent(_ctx(tmp_path, initialize_if_empty=True))


def test_bootstrap_absent_initializes_empty_remote_when_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.EMPTY)
    initialized: list = []
    monkeypatch.setattr(git_remote, "_initialize_and_publish", lambda ctx: initialized.append(ctx))

    git_remote.bootstrap_absent(_ctx(tmp_path, initialize_if_empty=True))
    assert initialized


def test_bootstrap_absent_refuses_empty_remote_without_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.EMPTY)
    with pytest.raises(SystemExit, match="is empty"):
        git_remote.bootstrap_absent(_ctx(tmp_path, initialize_if_empty=False))


# --- _publish_initial_branch (fatal + race-safe) -----------------------------


def test_failed_publish_is_fatal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_remote, "run_git", lambda *a, **k: _Result(1, "", "permission denied"))
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.EMPTY)
    with pytest.raises(SystemExit, match="failed to publish"):
        git_remote._publish_initial_branch(_ctx(tmp_path, initialize_if_empty=True))


def test_publish_race_with_concurrent_bootstrap_is_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_remote, "run_git", lambda *a, **k: _Result(1, "", "rejected: fetch first"))
    # Re-probe after the rejected push shows the branch now exists remotely.
    monkeypatch.setattr(git_remote, "classify_remote", lambda *a, **k: RemoteState.HAS_BRANCH)
    with pytest.raises(SystemExit, match="was being bootstrapped"):
        git_remote._publish_initial_branch(_ctx(tmp_path, initialize_if_empty=True))
