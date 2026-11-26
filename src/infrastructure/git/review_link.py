"""The address of a platform's "open a pull request" page for a pushed branch.

GitHub, GitLab and Azure DevOps each have a page that opens a pull (merge) request from a branch
against a base. Its address is built from the remote URL the branch was pushed to, in its ssh or
https form. Nothing is guessed: an unknown platform, or an ssh host alias that `~/.ssh/config` does
not resolve to a known host, gets no link, because a wrong link is worse than none.

GitLab is recognised at gitlab.com only. A self-hosted GitLab, GitHub Enterprise or Azure DevOps
Server lives at a host name that does not say which platform it runs.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, urlencode

from src.infrastructure.git.git_auth import read_remote_url, remote_urls
from src.infrastructure.git.git_repository_state import UPSTREAM_BRANCH

#: Resolves an ssh host alias to the host it names, or None when nothing resolves it.
HostResolver = Callable[[str], str | None]

_GITHUB = "github.com"
_GITLAB = "gitlab.com"
_AZURE_HOSTS = ("dev.azure.com", "ssh.dev.azure.com")
_AZURE_LEGACY_SUFFIX = ".visualstudio.com"
_KNOWN_HOSTS = (_GITHUB, _GITLAB, *_AZURE_HOSTS)


def new_pull_request_url(
    remote_url: str, *, branch: str, base: str, resolve_host: HostResolver | None = None
) -> str | None:
    """The new-pull-request page for `branch` against `base` on the platform `remote_url` names.

    `resolve_host` maps an ssh host alias (`github.com-personal`) to the host it stands for; the
    default asks ssh, reading only `~/.ssh/config`. None for an unknown platform or alias.
    """
    located = read_remote_url(remote_url)
    if located is None:
        return None
    host, path = located.host, located.path
    if not _is_known(host):
        over_ssh = located.protocol == "ssh"
        resolved = (resolve_host or resolve_ssh_host_alias)(host) if over_ssh else None
        if resolved is None or not _is_known(resolved):
            return None
        host = resolved
    segments = [segment for segment in path.strip("/").removesuffix(".git").split("/") if segment]
    if host == _GITHUB and len(segments) == 2:
        owner, repo = segments
        return f"https://github.com/{owner}/{repo}/compare/{quote(base, safe='')}...{quote(branch, safe='')}?expand=1"
    if host == _GITLAB and len(segments) >= 2:
        query = urlencode({"merge_request[source_branch]": branch, "merge_request[target_branch]": base})
        return f"https://gitlab.com/{'/'.join(segments)}/-/merge_requests/new?{query}"
    azure = _azure_project(host, segments)
    if azure is not None:
        organisation, project, repo = azure
        query = urlencode({"sourceRef": branch, "targetRef": base})
        return f"https://dev.azure.com/{organisation}/{project}/_git/{repo}/pullrequestcreate?{query}"
    return None


def review_url_for(repo: Path, *, branch: str, base: str = UPSTREAM_BRANCH) -> str | None:
    """The new-pull-request page for `branch` as `repo` pushes it (the push URL, else the fetch URL), against
    the branch the enterprise repository's reviews merge into unless *base* says otherwise."""
    urls = remote_urls(repo).pushed_to
    return new_pull_request_url(urls[-1], branch=branch, base=base) if urls else None


def resolve_ssh_host_alias(alias: str, *, config: Path | None = None) -> str | None:
    """The `HostName` `~/.ssh/config` gives `alias`, or None when it gives none.

    Asked of ssh (`ssh -G`), which owns the reading of its configuration, with only the user's file
    (`-F`) so a system-wide default cannot stand in for an entry the user wrote. ssh reports an
    unknown alias as its own host name, which is read as "not resolved".
    """
    source = config if config is not None else Path.home() / ".ssh" / "config"
    if not source.is_file():
        return None
    try:
        result = subprocess.run(
            ["ssh", "-G", "-F", str(source), alias],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "hostname":
            hostname = value.strip().lower()
            return hostname if hostname and hostname != alias.lower() else None
    return None


def _is_known(host: str) -> bool:
    return host in _KNOWN_HOSTS or host.endswith(_AZURE_LEGACY_SUFFIX)


def _azure_project(host: str, segments: list[str]) -> tuple[str, str, str] | None:
    """(organisation, project, repository) from an Azure DevOps remote, in any of its forms."""
    if host == "ssh.dev.azure.com" and len(segments) == 4 and segments[0] == "v3":
        return segments[1], segments[2], segments[3]
    if host == "dev.azure.com" and len(segments) == 4 and segments[2] == "_git":
        return segments[0], segments[1], segments[3]
    if host.endswith(_AZURE_LEGACY_SUFFIX):
        organisation = host.removesuffix(_AZURE_LEGACY_SUFFIX)
        if organisation == "vs-ssh" and len(segments) == 4 and segments[0] == "v3":
            return segments[1], segments[2], segments[3]
        if len(segments) == 3 and segments[1] == "_git":
            return organisation, segments[0], segments[2]
        if len(segments) == 4 and segments[2] == "_git" and segments[0] == "DefaultCollection":
            return organisation, segments[1], segments[3]
    return None
