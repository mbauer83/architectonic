"""Unit tests for git_remote decision logic (no subprocess): classification,
clone-vs-initialize, and fatal/race-safe publication."""

from __future__ import annotations

import subprocess
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


class TestProbeFailureDiagnostics:
    """Operators meet these errors on first boot; each must carry its fix, not a traceback."""

    def test_timeout_becomes_a_named_error_with_a_connectivity_hint(self, monkeypatch) -> None:
        def _hang(args, cwd=None, env=None):
            raise subprocess.TimeoutExpired(cmd=args, timeout=120)

        monkeypatch.setattr(git_remote, "run_git", _hang)
        with pytest.raises(SystemExit) as exc:
            git_remote.classify_remote("git@ssh.example.com:org/repo", "main")

        message = str(exc.value)
        assert "timed out" in message
        assert "HINT" in message and "ARCH_GIT_HTTPS_TOKEN" in message

    def test_host_key_failure_hint_names_the_key_variable(self) -> None:
        hint = git_remote._remote_failure_hint("Host key verification failed.", {})

        assert "ARCH_GIT_SSH_KEY" in hint
        assert "docs/reference/docker-compose.md" in hint

    def test_publickey_denial_hint_names_key_and_passphrase(self) -> None:
        hint = git_remote._remote_failure_hint(
            "git@host: Permission denied (publickey).", {}
        )

        assert "ARCH_GIT_SSH_KEY" in hint and "ARCH_GIT_SSH_PASSWORD" in hint

    def test_unresolvable_host_hint_points_at_dns_not_credentials(self) -> None:
        hint = git_remote._remote_failure_hint("fatal: Could not resolve host: your.git.host", {})

        assert "DNS" in hint
        assert "TOKEN" not in hint

    def test_an_unrecognised_error_adds_no_hint(self) -> None:
        assert git_remote._remote_failure_hint("something else entirely", {}) == ""

    def test_authentication_hint_distinguishes_configured_from_absent_credentials(self) -> None:
        configured = git_remote._remote_failure_hint(
            "fatal: Authentication failed", {"ARCH_GIT_HTTPS_TOKEN": "t"}
        )
        absent = git_remote._remote_failure_hint("fatal: Authentication failed", {})

        assert "ARE configured" in configured
        assert "no ARCH_GIT_HTTPS_* credential is set" in absent


class TestHintsReadTheEnvironmentGitWasGiven:
    """A hint that reads the process environment while git ran with another one contradicts
    the very command it is explaining — the parameter exists precisely because they differ."""

    def test_an_ssh_url_with_https_credentials_in_the_passed_env_is_diagnosed(self) -> None:
        hint = git_remote._credential_scheme_mismatch_hint(
            "git@host:org/repo", {"ARCH_GIT_HTTPS_TOKEN": "t"}
        )

        assert "this remote is SSH" in hint

    def test_credentials_present_only_in_the_process_environment_are_not_claimed(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "leaked-from-the-process")

        assert git_remote._credential_scheme_mismatch_hint("git@host:org/repo", {}) == ""

    def test_an_https_url_is_never_told_its_credentials_do_not_apply(self) -> None:
        hint = git_remote._credential_scheme_mismatch_hint(
            "https://host/org/repo", {"ARCH_GIT_HTTPS_TOKEN": "t"}
        )

        assert hint == ""

    def test_a_configured_ssh_command_means_the_scheme_is_deliberate(self) -> None:
        hint = git_remote._credential_scheme_mismatch_hint(
            "git@host:org/repo", {"ARCH_GIT_HTTPS_TOKEN": "t", "GIT_SSH_COMMAND": "ssh -i k"}
        )

        assert hint == ""

    def test_no_env_passed_falls_back_to_the_process_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "t")

        assert git_remote._effective_env(None).get("ARCH_GIT_HTTPS_TOKEN") == "t"
        assert git_remote._effective_env({}).get("ARCH_GIT_HTTPS_TOKEN") is None
