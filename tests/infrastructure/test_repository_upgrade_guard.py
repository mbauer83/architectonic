"""Tests for the D17 `--commit` guard: backend-serving-target-repo (the only blocking gate)
plus the informational (never-blocking) dirty-file-overlap helper."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.repository_upgrade import guard


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_dirty_worktree_files_reports_untracked_and_modified(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "committed.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)

    assert guard.dirty_worktree_files(repo) == []

    (repo / "committed.txt").write_text("b", encoding="utf-8")
    (repo / "untracked.txt").write_text("c", encoding="utf-8")

    dirty = guard.dirty_worktree_files(repo)
    assert "committed.txt" in dirty
    assert "untracked.txt" in dirty


def test_conflicting_dirty_files_excludes_unrelated_dirty_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "touched.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "touched.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    (repo / "touched.txt").write_text("b", encoding="utf-8")
    (repo / "unrelated.txt").write_text("c", encoding="utf-8")

    overlap = guard.conflicting_dirty_files(repo, frozenset({"touched.txt"}))

    assert overlap == ["touched.txt"]


def test_conflicting_dirty_files_empty_when_no_overlap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "unrelated.txt").write_text("c", encoding="utf-8")

    assert guard.conflicting_dirty_files(repo, frozenset({"touched.txt"})) == []


def test_probe_backend_identity_none_on_bad_response(monkeypatch) -> None:
    def fake_urlopen(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(guard, "urlopen", fake_urlopen)
    assert guard.probe_backend_identity("http://127.0.0.1:1") is None


def test_probe_backend_identity_parses_valid_response(monkeypatch) -> None:
    import json

    class _Resp:
        status = 200

        def read(self):
            return json.dumps({"repo_roots": ["/a", "/b"], "software_version": "1.2.3"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(guard, "urlopen", lambda *a, **k: _Resp())
    identity = guard.probe_backend_identity("http://127.0.0.1:1")
    assert identity is not None
    assert identity.repo_roots == ("/a", "/b")
    assert identity.software_version == "1.2.3"


def test_check_backend_not_serving_no_block_when_backend_not_responding(tmp_path: Path) -> None:
    result = guard.check_backend_not_serving(tmp_path, backend_responding=False, identity=None)
    assert result.blocked is False


def test_check_backend_not_serving_fails_closed_on_missing_endpoint(tmp_path: Path) -> None:
    result = guard.check_backend_not_serving(tmp_path, backend_responding=True, identity=None)
    assert result.blocked is True
    assert "backend-identity" in result.reason


def test_check_backend_not_serving_blocks_when_target_is_served(tmp_path: Path) -> None:
    identity = guard.BackendIdentity(repo_roots=(str(tmp_path.resolve()),), software_version="9.9.9")
    result = guard.check_backend_not_serving(tmp_path, backend_responding=True, identity=identity)
    assert result.blocked is True
    assert "9.9.9" in result.reason


def test_check_backend_not_serving_does_not_block_unrelated_backend(tmp_path: Path) -> None:
    other = tmp_path.parent / "unrelated-repo"
    identity = guard.BackendIdentity(repo_roots=(str(other),), software_version="9.9.9")
    result = guard.check_backend_not_serving(tmp_path, backend_responding=True, identity=identity)
    assert result.blocked is False
