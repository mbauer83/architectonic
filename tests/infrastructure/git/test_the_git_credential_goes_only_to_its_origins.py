"""The git credential is given only to the origins it was collected for.

The askpass helper answered every `Username…`/`Password…` prompt with the configured token, whichever
origin git was asking for — a redirect, a submodule or a second remote received it, and a plain-http
origin received an https remote's token in clear. It also answered any other prompt (an ssh password
login, a host-key question) with the key passphrase. Credentials now carry the origins they belong to,
and the helper answers only those, and gives the passphrase only to ssh's passphrase prompt.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.infrastructure.git.git_askpass import build_git_env, create_askpass_script
from src.infrastructure.git.git_auth import (
    GitCredentials,
    credential_origins,
)

_TOKEN = "s3cret-token"
_PASSPHRASE = "key-passphrase"


@pytest.fixture
def askpass() -> Iterator[Path]:
    path = create_askpass_script()
    yield path
    path.unlink(missing_ok=True)


def _answer(askpass: Path, prompt: str, credentials: GitCredentials) -> str:
    env = build_git_env(credentials, askpass)
    env.pop("ARCH_GIT_HTTPS_TOKEN", None)
    completed = subprocess.run([str(askpass), prompt], env=env, capture_output=True, text=True, timeout=10)
    return completed.stdout.rstrip("\n")


def _held(*urls: str) -> GitCredentials:
    return GitCredentials(
        ssh_passphrase=_PASSPHRASE, https_username="me", https_password=_TOKEN
    ).for_origins(urls)


def test_the_configured_origin_gets_the_username_and_the_token(askpass: Path) -> None:
    credentials = _held("https://git.example.com/team/repo.git")
    assert _answer(askpass, "Username for 'https://git.example.com': ", credentials) == "me"
    assert _answer(askpass, "Password for 'https://me@git.example.com': ", credentials) == _TOKEN


def test_another_host_gets_nothing(askpass: Path) -> None:
    credentials = _held("https://git.example.com/team/repo.git")
    assert _answer(askpass, "Password for 'https://me@attacker.example.net': ", credentials) == ""
    assert _answer(askpass, "Username for 'https://attacker.example.net': ", credentials) == ""


def test_the_same_host_over_plain_http_gets_nothing(askpass: Path) -> None:
    credentials = _held("https://git.example.com/team/repo.git")
    assert _answer(askpass, "Password for 'http://me@git.example.com': ", credentials) == ""


def test_a_port_is_part_of_the_origin(askpass: Path) -> None:
    credentials = _held("https://git.example.com:8443/team/repo.git")
    assert _answer(askpass, "Password for 'https://me@git.example.com:8443': ", credentials) == _TOKEN
    assert _answer(askpass, "Password for 'https://me@git.example.com': ", credentials) == ""


def test_the_host_compares_without_case(askpass: Path) -> None:
    credentials = _held("https://Git.Example.com/team/repo.git")
    assert _answer(askpass, "Password for 'https://me@git.EXAMPLE.com': ", credentials) == _TOKEN


def test_credentials_bound_to_no_origin_answer_nothing(askpass: Path) -> None:
    credentials = GitCredentials(https_username="me", https_password=_TOKEN)
    assert _answer(askpass, "Password for 'https://me@git.example.com': ", credentials) == ""


def test_the_passphrase_goes_only_to_the_passphrase_prompt(askpass: Path) -> None:
    credentials = _held()
    assert _answer(askpass, "Enter passphrase for key '/home/me/.ssh/id_ed25519': ", credentials) == _PASSPHRASE
    assert _answer(askpass, "me@git.example.com's password: ", credentials) == ""
    assert _answer(askpass, "Are you sure you want to continue connecting (yes/no)? ", credentials) == ""


def test_an_environment_token_is_bound_the_same_way(askpass: Path) -> None:
    credentials = GitCredentials().for_origins(["https://git.example.com/team/repo.git"])
    env = {**build_git_env(credentials, askpass), "ARCH_GIT_HTTPS_TOKEN": _TOKEN}
    run = lambda prompt: subprocess.run(  # noqa: E731 - one call shape, two prompts
        [str(askpass), prompt], env=env, capture_output=True, text=True, timeout=10
    ).stdout.rstrip("\n")
    assert run("Password for 'https://x-access-token@git.example.com': ") == _TOKEN
    assert run("Password for 'https://x-access-token@elsewhere.example.org': ") == ""


def test_origins_are_read_from_https_remotes_only() -> None:
    assert credential_origins([
        "https://git.example.com/a.git",
        "http://plain.example.com/b.git",
        "git@ssh.example.com:c.git",
        "ssh://ssh.example.com/d.git",
        "/local/path",
        "https://user:tok@Host.Example.com:8443/e.git",
    ]) == frozenset({"https://git.example.com", "http://plain.example.com", "https://host.example.com:8443"})


def test_collected_credentials_are_bound_to_the_remotes_they_were_collected_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.git.git_auth import collect_credentials

    monkeypatch.setenv("ARCH_GIT_HTTPS_TOKEN", _TOKEN)
    monkeypatch.delenv("ARCH_GIT_HTTPS_TOKEN_FILE", raising=False)
    credentials = collect_credentials(["https://git.example.com/team/repo.git"])
    assert credentials is not None
    assert credentials.https_origins == frozenset({"https://git.example.com"})


def test_the_helper_is_a_posix_shell_script() -> None:
    path = create_askpass_script()
    try:
        assert path.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
        assert os.access(path, os.X_OK)
    finally:
        path.unlink(missing_ok=True)
