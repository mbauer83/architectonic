"""Startup must not accept wrong git credentials silently. Interactively-entered credentials that
are rejected are re-prompted (looping until valid or Ctrl-C); environment / non-interactive ones
fail loudly. Covers the auth-rejection probe (only a genuine auth failure counts) and the
collect-verify-reprompt orchestration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.infrastructure.git import git_auth
from src.infrastructure.git.git_auth import (
    GitCredentialError,
    GitCredentials,
    _auth_rejection,
    collect_verified_credentials,
    verify_credentials,
)


class _Result:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeStdin:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class TestAuthRejection:
    def test_clean_auth_returns_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result(0))
        assert _auth_rejection(tmp_path, {}) is None

    def test_rejected_credentials_return_the_reason(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result(128, stderr=b"Permission denied (publickey)."))
        reason = _auth_rejection(tmp_path, {})
        assert reason is not None
        assert "permission denied" in reason.lower()

    def test_non_auth_error_is_not_a_rejection(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        network_err = _Result(128, stderr=b"Could not resolve host example.com")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: network_err)
        assert _auth_rejection(tmp_path, {}) is None

    def test_timeout_is_not_a_rejection(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        def _timeout(*a: object, **k: object) -> None:
            raise subprocess.TimeoutExpired(cmd="git", timeout=15)

        monkeypatch.setattr(subprocess, "run", _timeout)
        assert _auth_rejection(tmp_path, {}) is None


class TestVerifyCredentials:
    def test_repos_without_remote_are_skipped(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(git_auth, "detect_remote_protocol", lambda p: None)
        monkeypatch.setattr(git_auth, "_auth_rejection", lambda *a: pytest.fail("must not probe a remoteless repo"))
        assert verify_credentials([tmp_path], {}) == []

    def test_collects_rejections(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(git_auth, "detect_remote_protocol", lambda p: "ssh")
        monkeypatch.setattr(git_auth, "_auth_rejection", lambda p, e: "permission denied")
        assert verify_credentials([tmp_path], {}) == [(tmp_path, "permission denied")]


class TestCollectVerifiedCredentials:
    """The collect → verify → (re-prompt | fail-loud) orchestration."""

    def _wire(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, env: bool, tty: bool) -> None:
        monkeypatch.setattr(git_auth, "create_askpass_script", lambda: tmp_path / "askpass.sh")
        # env is the passphrase so verify can distinguish which creds it was handed.
        monkeypatch.setattr(git_auth, "build_git_env", lambda c, a: {"pp": c.ssh_passphrase or ""})
        monkeypatch.setattr(git_auth, "_has_env_credentials", lambda: env)
        monkeypatch.setattr(sys, "stdin", _FakeStdin(tty))

    def test_returns_none_when_no_credentials_needed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(git_auth, "collect_credentials", lambda t: None)
        assert collect_verified_credentials([tmp_path]) is None

    def test_valid_first_try_returns_credentials(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._wire(monkeypatch, tmp_path, env=False, tty=True)
        monkeypatch.setattr(git_auth, "collect_credentials", lambda t: GitCredentials(ssh_passphrase="ok"))
        monkeypatch.setattr(git_auth, "verify_credentials", lambda p, e: [])
        assert collect_verified_credentials([tmp_path]).ssh_passphrase == "ok"  # type: ignore[union-attr]

    def test_environment_credentials_fail_loudly(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._wire(monkeypatch, tmp_path, env=True, tty=True)  # env-sourced → non-repromptable
        monkeypatch.setattr(git_auth, "collect_credentials", lambda t: GitCredentials(ssh_passphrase="wrong"))
        monkeypatch.setattr(git_auth, "verify_credentials", lambda p, e: [(tmp_path, "permission denied")])
        with pytest.raises(GitCredentialError, match="rejected"):
            collect_verified_credentials([tmp_path])

    def test_non_interactive_fails_loudly(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._wire(monkeypatch, tmp_path, env=False, tty=False)  # no TTY → cannot re-prompt
        monkeypatch.setattr(git_auth, "collect_credentials", lambda t: GitCredentials(ssh_passphrase="wrong"))
        monkeypatch.setattr(git_auth, "verify_credentials", lambda p, e: [(tmp_path, "permission denied")])
        with pytest.raises(GitCredentialError):
            collect_verified_credentials([tmp_path])

    def test_interactive_reprompts_until_valid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(monkeypatch, tmp_path, env=False, tty=True)  # TTY, no env → re-promptable
        entered = iter([GitCredentials(ssh_passphrase="wrong"), GitCredentials(ssh_passphrase="right")])
        monkeypatch.setattr(git_auth, "collect_credentials", lambda t: next(entered))
        monkeypatch.setattr(
            git_auth, "verify_credentials",
            lambda p, e: [] if e.get("pp") == "right" else [(tmp_path, "permission denied")],
        )
        result = collect_verified_credentials([tmp_path])
        assert result is not None and result.ssh_passphrase == "right"
        assert "rejected" in capsys.readouterr().err.lower()  # the operator was told
