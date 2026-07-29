"""HTTPS PAT support: a token alone (no username) must authenticate.

Covers `resolve_https_from_env` precedence and the generated askpass script so the
docker-compose `ARCH_GIT_HTTPS_TOKEN` path works whether git is handed resolved
credentials or just the raw process environment.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from src.infrastructure.git import git_auth

_HTTPS_ENV_VARS = (
    "ARCH_GIT_HTTPS_USERNAME",
    "ARCH_GIT_HTTPS_PASSWORD",
    "ARCH_GIT_HTTPS_TOKEN",
    "ARCH_GIT_HTTPS_TOKEN_FILE",
)


@pytest.fixture(autouse=True)
def _clear_https_env(monkeypatch):  # type: ignore[no-untyped-def]
    for var in _HTTPS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_token_alone_supplies_password_and_default_username(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "ghp_secret")
    username, password = git_auth.resolve_https_from_env()
    assert username == git_auth._DEFAULT_TOKEN_USERNAME
    assert password == "ghp_secret"


def test_explicit_username_overrides_token_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "ghp_secret")
    monkeypatch.setenv("ARCH_GIT_HTTPS_USERNAME", "ci-bot")
    username, password = git_auth.resolve_https_from_env()
    assert (username, password) == ("ci-bot", "ghp_secret")


def test_token_file_supplies_credentials(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    token_file = tmp_path / "pat"
    token_file.write_text("ghp_from_file\n")  # trailing newline must be stripped
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN_FILE", str(token_file))
    username, password = git_auth.resolve_https_from_env()
    assert username == git_auth._DEFAULT_TOKEN_USERNAME
    assert password == "ghp_from_file"


def test_inline_token_takes_precedence_over_token_file(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    token_file = tmp_path / "pat"
    token_file.write_text("from_file")
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "inline")
    _username, password = git_auth.resolve_https_from_env()
    assert password == "inline"


def test_register_token_file_sets_path_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    git_auth.register_token_file("/run/secrets/git_pat")
    assert os.environ["ARCH_GIT_HTTPS_TOKEN_FILE"] == "/run/secrets/git_pat"
    # A falsy value is a no-op (flag not supplied).
    monkeypatch.delenv("ARCH_GIT_HTTPS_TOKEN_FILE", raising=False)
    git_auth.register_token_file(None)
    assert "ARCH_GIT_HTTPS_TOKEN_FILE" not in os.environ


def test_daemon_handoff_omits_token_value_when_file_used(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    token_file = tmp_path / "pat"
    token_file.write_text("ghp_from_file")
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN_FILE", str(token_file))
    creds = git_auth.collect_credentials(["https://github.com/acme/repo.git"])
    assert creds is not None and creds.https_password == "ghp_from_file"
    # The daemon inherits only the path (already in env), never the expanded token value.
    overrides = git_auth.credentials_to_env_overrides(creds)
    assert "ARCH_GIT_HTTPS_PASSWORD" not in overrides
    assert "ARCH_GIT_HTTPS_USERNAME" not in overrides


def test_explicit_password_takes_precedence_over_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "ghp_token")
    monkeypatch.setenv("ARCH_GIT_HTTPS_USERNAME", "ci-bot")
    monkeypatch.setenv("ARCH_GIT_HTTPS_PASSWORD", "explicit-pw")
    username, password = git_auth.resolve_https_from_env()
    assert (username, password) == ("ci-bot", "explicit-pw")
    # No username default is injected when a password was given explicitly.


def test_no_credentials_resolves_to_none() -> None:
    assert git_auth.resolve_https_from_env() == (None, None)


def test_collect_credentials_uses_token_for_https_remote(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # The path arch-backend / arch-init take: an HTTPS remote + a token env var (no username,
    # no TTY) must yield usable credentials without prompting.
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "ghp_secret")
    creds = git_auth.collect_credentials(["https://github.com/acme/repo.git"])
    assert creds is not None
    assert creds.has_https
    assert creds.https_username == git_auth._DEFAULT_TOKEN_USERNAME
    assert creds.https_password == "ghp_secret"

    # And the token propagates into the daemon hand-off env (credentials_to_env_overrides).
    overrides = git_auth.credentials_to_env_overrides(creds)
    assert overrides["ARCH_GIT_HTTPS_USERNAME"] == git_auth._DEFAULT_TOKEN_USERNAME
    assert overrides["ARCH_GIT_HTTPS_PASSWORD"] == "ghp_secret"


def _run_askpass(script_path, prompt, env):  # type: ignore[no-untyped-def]
    return subprocess.run(
        [str(script_path), prompt], capture_output=True, text=True, env=env, timeout=5
    ).stdout.strip()


def test_askpass_script_honours_token_only(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", "ghp_secret")
    script = git_auth.create_askpass_script()
    try:
        env = {"ARCH_GIT_HTTPS_TOKEN": "ghp_secret"}
        assert _run_askpass(script, "Username for 'https://github.com': ", env) == "x-access-token"
        assert _run_askpass(script, "Password for 'https://github.com': ", env) == "ghp_secret"
    finally:
        script.unlink(missing_ok=True)


def test_askpass_script_prefers_explicit_username(tmp_path) -> None:  # type: ignore[no-untyped-def]
    script = git_auth.create_askpass_script()
    try:
        env = {"ARCH_GIT_HTTPS_TOKEN": "ghp_secret", "ARCH_GIT_HTTPS_USERNAME": "ci-bot"}
        assert _run_askpass(script, "Username for 'https://x': ", env) == "ci-bot"
        assert _run_askpass(script, "Password for 'https://x': ", env) == "ghp_secret"
    finally:
        script.unlink(missing_ok=True)
