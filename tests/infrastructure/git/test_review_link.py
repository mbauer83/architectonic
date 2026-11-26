"""The "open the pull request" link, over the remote URL forms each platform uses.

One function builds it; unknown platforms, and ssh host aliases that `~/.ssh/config` does not resolve
to a known host, get no link rather than a guessed one.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git.review_link import new_pull_request_url, resolve_ssh_host_alias, review_url_for

BRANCH = "arch/work-20261126-101500"
BASE = "main"

_GITHUB = "https://github.com/acme/enterprise/compare/main...arch%2Fwork-20261126-101500?expand=1"
_GITLAB_QUERY = (
    "merge_request%5Bsource_branch%5D=arch%2Fwork-20261126-101500&merge_request%5Btarget_branch%5D=main"
)
_AZURE = (
    "https://dev.azure.com/acme/Architecture/_git/enterprise/pullrequestcreate"
    "?sourceRef=arch%2Fwork-20261126-101500&targetRef=main"
)


def _no_aliases(alias: str) -> str | None:
    return None


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/acme/enterprise.git", _GITHUB),
        ("https://github.com/acme/enterprise", _GITHUB),
        ("https://user@github.com/acme/enterprise.git", _GITHUB),
        ("git@github.com:acme/enterprise.git", _GITHUB),
        ("ssh://git@github.com/acme/enterprise.git", _GITHUB),
        ("https://gitlab.com/acme/platform/enterprise.git",
         f"https://gitlab.com/acme/platform/enterprise/-/merge_requests/new?{_GITLAB_QUERY}"),
        ("git@gitlab.com:acme/enterprise.git",
         f"https://gitlab.com/acme/enterprise/-/merge_requests/new?{_GITLAB_QUERY}"),
        ("https://acme@dev.azure.com/acme/Architecture/_git/enterprise", _AZURE),
        ("https://dev.azure.com/acme/Architecture/_git/enterprise", _AZURE),
        ("git@ssh.dev.azure.com:v3/acme/Architecture/enterprise", _AZURE),
        ("https://acme.visualstudio.com/Architecture/_git/enterprise", _AZURE),
        ("https://acme.visualstudio.com/DefaultCollection/Architecture/_git/enterprise", _AZURE),
        ("acme@vs-ssh.visualstudio.com:v3/acme/Architecture/enterprise", _AZURE),
    ],
)
def test_each_platform_form(remote: str, expected: str) -> None:
    assert new_pull_request_url(remote, branch=BRANCH, base=BASE, resolve_host=_no_aliases) == expected


@pytest.mark.parametrize(
    "remote",
    [
        "https://git.example.invalid/acme/enterprise.git",
        "git@bitbucket.org:acme/enterprise.git",
        "/srv/repos/enterprise.git",
        "file:///srv/repos/enterprise.git",
        "https://github.com/acme",  # no repository segment
        "https://dev.azure.com/acme/Architecture/enterprise",  # no _git segment
    ],
)
def test_unknown_platforms_and_shapes_get_no_link(remote: str) -> None:
    assert new_pull_request_url(remote, branch=BRANCH, base=BASE, resolve_host=_no_aliases) is None


def test_an_ssh_alias_maps_to_the_host_its_config_names() -> None:
    resolved = new_pull_request_url(
        "github.com-personal:acme/enterprise.git", branch=BRANCH, base=BASE,
        resolve_host=lambda alias: "github.com" if alias == "github.com-personal" else None,
    )
    assert resolved == _GITHUB


def test_an_unresolved_alias_gets_no_link() -> None:
    assert new_pull_request_url(
        "github.com-personal:acme/enterprise.git", branch=BRANCH, base=BASE, resolve_host=_no_aliases
    ) is None


def test_an_alias_resolving_to_an_unknown_host_gets_no_link() -> None:
    assert new_pull_request_url(
        "work:acme/enterprise.git", branch=BRANCH, base=BASE, resolve_host=lambda _alias: "git.internal",
    ) is None


def test_an_https_host_is_never_resolved_as_an_alias() -> None:
    def refuse(alias: str) -> str | None:
        raise AssertionError("an https host is not an ssh alias")

    assert new_pull_request_url(
        "https://code.example.invalid/acme/enterprise.git", branch=BRANCH, base=BASE, resolve_host=refuse
    ) is None


@pytest.mark.skipif(shutil.which("ssh") is None, reason="needs an ssh client to read its configuration")
def test_aliases_are_read_from_the_ssh_config_by_ssh(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host github.com-personal\n    HostName github.com\n    User git\n", encoding="utf-8")
    assert resolve_ssh_host_alias("github.com-personal", config=config) == "github.com"
    assert resolve_ssh_host_alias("not-configured", config=config) is None
    assert resolve_ssh_host_alias("github.com-personal", config=tmp_path / "absent") is None


def test_a_pending_submission_reports_its_link_and_another_state_does_not(tmp_path: Path) -> None:
    from src.infrastructure.git import enterprise_sync_state
    from src.infrastructure.rest.routers.sync.status_cache import _review_url_while_pending

    repo = tmp_path / "enterprise"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:acme/enterprise.git"], cwd=repo, check=True)
    enterprise_sync_state.replace_lifecycle(repo, status="accumulating", branch=BRANCH)
    assert _review_url_while_pending(repo) is None
    enterprise_sync_state.replace_lifecycle(repo, status="pending", branch=BRANCH, pushed_at="2026-11-26T10:15:00Z")
    assert _review_url_while_pending(repo) == _GITHUB


def test_the_push_url_is_the_one_linked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://mirror.example.invalid/acme/enterprise.git"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "--push", "origin", "git@github.com:acme/enterprise.git"],
        cwd=repo, check=True,
    )
    assert review_url_for(repo, branch=BRANCH, base=BASE) == _GITHUB
