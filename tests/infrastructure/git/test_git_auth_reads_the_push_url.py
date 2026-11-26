"""Credentials are prepared for every protocol a repository's remote is fetched *or pushed* over.

Regression: `detect_remote_protocol` read only `git remote get-url origin`, the fetch URL. A remote
that fetches over https and pushes over ssh was taken for https alone, so no SSH askpass was wired
and a submit failed with `ssh_askpass: exec(/usr/bin/ssh-askpass): No such file or directory …
Permission denied (publickey)`. Fixture repositories only: nothing here reaches a network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import git_auth

_FETCH = "https://git.example.invalid/acme/repo.git"
_PUSH = "git@git.example.invalid:acme/repo.git"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def split_remote(tmp_path: Path) -> Path:
    """A repository whose origin fetches over https and pushes over ssh."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", _FETCH)
    _git(repo, "remote", "set-url", "--push", "origin", _PUSH)
    return repo


@pytest.fixture(autouse=True)
def _no_credentials_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "ARCH_GIT_SSH_PASSWORD", "ARCH_GIT_HTTPS_USERNAME", "ARCH_GIT_HTTPS_PASSWORD",
        "ARCH_GIT_HTTPS_TOKEN", "ARCH_GIT_HTTPS_TOKEN_FILE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_both_the_fetch_and_the_push_url_are_read(split_remote: Path) -> None:
    assert git_auth.remote_urls(split_remote) == (_FETCH, _PUSH)
    assert git_auth.detect_remote_protocols(split_remote) == frozenset({"https", "ssh"})


def test_a_push_insteadof_rewrite_counts_as_the_push_url(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", _FETCH)
    _git(repo, "config", "url.git@git.example.invalid:.pushInsteadOf", "https://git.example.invalid/")
    assert git_auth.detect_remote_protocols(repo) == frozenset({"https", "ssh"})


def test_an_ssh_passphrase_is_kept_for_a_remote_that_only_pushes_over_ssh(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARCH_GIT_SSH_PASSWORD", "open sesame")
    creds = git_auth.collect_credentials([split_remote])
    assert creds is not None
    assert creds.ssh_passphrase == "open sesame"


def test_probing_reaches_the_push_url(split_remote: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probed: list[str] = []

    def probe(url: str, cwd: Path) -> bool:
        probed.append(url)
        return url == _PUSH

    monkeypatch.setattr(git_auth, "_probe_url_needs_credential", probe)
    assert git_auth.probe_needs_credential(split_remote) is True
    assert probed == [_FETCH, _PUSH]


def test_verification_checks_the_push_url_of_the_protocol_asked_about(
    split_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def rejection(target: Path, url: str, env: dict[str, str]) -> str | None:
        asked.append(url)
        return "Permission denied (publickey)." if url == _PUSH else None

    monkeypatch.setattr(git_auth, "_auth_rejection", rejection)
    failures = git_auth.verify_credentials([split_remote], {}, protocols=frozenset({"ssh"}))
    assert asked == [_PUSH]
    assert failures == [(split_remote, "Permission denied (publickey).")]


@pytest.mark.parametrize(
    ("url", "protocol"),
    [
        ("git@github.com:acme/repo.git", "ssh"),
        ("github.com-personal:acme/repo.git", "ssh"),
        ("ssh://git@host:2222/acme/repo.git", "ssh"),
        ("https://host/acme/repo.git", "https"),
        ("/srv/git/repo.git", None),
        ("file:///srv/git/repo.git", None),
        ("git://host/repo.git", None),
        ("C:/repos/repo.git", None),
    ],
)
def test_url_forms(url: str, protocol: str | None) -> None:
    assert git_auth._protocol_from_url(url) == protocol
