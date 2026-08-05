"""Tests for backend_state.py I/O functions.

Covers: _state_dir (env var, file-based start), backend_log_path,
read_backend_state (missing file, valid, invalid JSON, wrong types),
_process_exists, write_backend_state, remove_backend_state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.backend.backend_process import _read_process_state
from src.infrastructure.backend.backend_state import (
    _process_exists,
    _state_dir,
    backend_log_path,
    backend_state_path,
    read_backend_state,
    remove_backend_state,
    remove_own_backend_state,
    write_backend_state,
)

# ── _state_dir ────────────────────────────────────────────────────────────────


class TestStateDir:
    def test_uses_env_var_when_set(self, tmp_path: Path, monkeypatch) -> None:
        target = tmp_path / "custom-state"
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(target))
        result = _state_dir()
        assert result == target.expanduser().resolve()

    def test_uses_workspace_root_arch_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ARCH_BACKEND_STATE_DIR", raising=False)
        with patch("src.infrastructure.backend.backend_state.workspace_root", return_value=tmp_path):
            result = _state_dir()
        assert result == tmp_path / ".arch"

    def test_falls_back_to_cwd_arch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ARCH_BACKEND_STATE_DIR", raising=False)
        with patch("src.infrastructure.backend.backend_state.workspace_root", return_value=None):
            result = _state_dir(start=tmp_path)
        assert result == tmp_path / ".arch"

    def test_file_path_uses_parent(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ARCH_BACKEND_STATE_DIR", raising=False)
        fake_file = tmp_path / "somefile.txt"
        fake_file.touch()
        with patch("src.infrastructure.backend.backend_state.workspace_root", return_value=None):
            result = _state_dir(start=fake_file)
        assert result == tmp_path / ".arch"


# ── backend_log_path ──────────────────────────────────────────────────────────


class TestBackendLogPath:
    def test_returns_configured_absolute_path(self, monkeypatch) -> None:
        abs_path = Path("/tmp/test-backend.log")
        with patch("src.infrastructure.backend.backend_state.configured_backend_log_path", return_value=str(abs_path)):
            result = backend_log_path()
        assert result == abs_path

    def test_relative_path_with_workspace_root(self, tmp_path: Path) -> None:
        with patch("src.infrastructure.backend.backend_state.configured_backend_log_path", return_value="backend.log"):
            with patch("src.infrastructure.backend.backend_state.workspace_root", return_value=tmp_path):
                result = backend_log_path()
        assert result == (tmp_path / "backend.log").resolve()

    def test_relative_path_without_workspace_root(self, tmp_path: Path) -> None:
        with patch("src.infrastructure.backend.backend_state.configured_backend_log_path", return_value="backend.log"):
            with patch("src.infrastructure.backend.backend_state.workspace_root", return_value=None):
                result = backend_log_path(start=tmp_path)
        assert result == (tmp_path / "backend.log").resolve()


# ── read_backend_state ────────────────────────────────────────────────────────


class TestReadBackendState:
    def _state_path(self, tmp_path: Path) -> Path:
        state_dir = tmp_path / ".arch"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "backend.pid"

    def test_returns_none_when_file_missing(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        result = read_backend_state()
        assert result is None

    def test_returns_state_for_valid_file(self, tmp_path: Path, monkeypatch) -> None:
        path = self._state_path(tmp_path)
        path.write_text(json.dumps({"pid": 12345, "port": 8080}), encoding="utf-8")
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        result = read_backend_state()
        assert result is not None
        assert result["pid"] == 12345
        assert result["port"] == 8080

    def test_returns_none_for_invalid_json(self, tmp_path: Path, monkeypatch) -> None:
        path = self._state_path(tmp_path)
        path.write_text("not valid json {{", encoding="utf-8")
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        result = read_backend_state()
        assert result is None

    def test_returns_none_when_pid_is_string(self, tmp_path: Path, monkeypatch) -> None:
        path = self._state_path(tmp_path)
        path.write_text(json.dumps({"pid": "not-int", "port": 8080}), encoding="utf-8")
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        result = read_backend_state()
        assert result is None

    def test_returns_none_when_not_a_dict(self, tmp_path: Path, monkeypatch) -> None:
        path = self._state_path(tmp_path)
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        result = read_backend_state()
        assert result is None


# ── _process_exists ───────────────────────────────────────────────────────────


class TestProcessExists:
    def test_current_process_exists(self) -> None:
        result = _process_exists(os.getpid())
        assert result is True

    def test_nonexistent_pid_returns_false(self) -> None:
        # PID 2^30 is unlikely to exist
        result = _process_exists(2**30)
        assert result is False

    def test_zombie_counts_as_gone(self) -> None:
        """Regression: a SIGKILLed backend whose spawner never reaped it stays a
        zombie — os.kill(pid, 0) still succeeds, so stop_backend waited out its
        full timeout and reported 'failed to stop' for an already-dead process.

        Spawned rather than forked. `os.fork()` in a process with threads — which pytest-xdist's
        worker is — warns for good reason: the child inherits the lock state of every thread that was
        not running, and a deadlock there would hang the whole run rather than fail it. `Popen` of a
        process that exits at once produces the same zombie, because the test simply does not `wait`
        for it yet, which is the state under test.
        """
        child = subprocess.Popen([sys.executable, "-c", ""])  # exits immediately, unreaped
        try:
            deadline = time.monotonic() + 5.0
            while _read_process_state(child.pid) != "Z" and time.monotonic() < deadline:
                time.sleep(0.01)
            assert _read_process_state(child.pid) == "Z"
            assert _process_exists(child.pid) is False
        finally:
            child.wait()


# ── write_backend_state ───────────────────────────────────────────────────────


class TestWriteBackendState:
    def test_writes_pid_and_port(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        path = write_backend_state(port=9090, pid=42)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["pid"] == 42
        assert data["port"] == 9090

    def test_uses_current_pid_when_not_provided(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        write_backend_state(port=7070)
        path = backend_state_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()


# ── remove_backend_state ──────────────────────────────────────────────────────


class TestRemoveBackendState:
    def test_removes_existing_state_file(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        write_backend_state(port=6060, pid=1)
        path = backend_state_path()
        assert path.exists()
        remove_backend_state()
        assert not path.exists()

    def test_silently_ignores_missing_file(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        remove_backend_state()  # should not raise


class TestRemoveOwnBackendState:
    """Only the process the record names may remove it.

    A serving backend's record is the workspace's pointer to it, and every process in the workspace
    resolves the same path. An unconditional delete on the way out let a short-lived one — a test
    driving the entry point, a wrapper that got as far as the teardown — orphan a live backend:
    `--status` had to fall back to identifying it by what it serves, and `--stop` had no pointer at all.
    """

    def test_removes_the_record_this_process_wrote(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        write_backend_state(port=8188)
        path = backend_state_path()
        assert path.exists()

        remove_own_backend_state()

        assert not path.exists()

    def test_leaves_a_record_that_names_another_process(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
        write_backend_state(port=8188, pid=os.getpid() + 1)
        path = backend_state_path()

        remove_own_backend_state()

        assert path.exists(), "a live backend's pointer must survive another process's teardown"
        assert json.loads(path.read_text(encoding="utf-8"))["port"] == 8188

    def test_silently_ignores_a_missing_record(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))

        remove_own_backend_state()  # should not raise
