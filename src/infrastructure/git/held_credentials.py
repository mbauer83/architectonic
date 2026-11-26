"""The git credentials this process holds, and the askpass environment wired from them.

One owner for the credentials a running backend uses. They arrive two ways: collected before
startup (a terminal prompt or the environment) and handed to `GitSyncManager`, or supplied later
through the GUI when an operation was refused for want of one. Both end here, so the askpass helper
and the environment every git call reads (`git_env`) are built in one place.

Held in memory for the process lifetime. Nothing here writes a credential to disk or to a log: the
askpass helper is a script that reads the secret from the environment of the git process it is
handed to, and `GitCredentials` keeps its secrets out of its `repr`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from pathlib import Path

from src.infrastructure.git import git_env
from src.infrastructure.git.git_auth import (
    GitCredentials,
    GitCredentialsRequired,
    RemoteProtocol,
    build_git_env,
    create_askpass_script,
    protocol_of_url,
    remote_urls,
    verify_credentials,
)

_lock = threading.Lock()
_credentials: GitCredentials | None = None
_askpass: Path | None = None


def hold(credentials: GitCredentials | None) -> None:
    """Hold `credentials` and wire every later git call to answer prompts from them.

    None holds nothing and leaves git with the process environment (an ssh-agent, a credential
    helper), which is what a workspace whose remotes need no credential runs with.
    """
    global _credentials, _askpass
    with _lock:
        _credentials = credentials
        if credentials is None or not (credentials.has_ssh or credentials.has_https):
            git_env.set_ssh_env(None)
            return
        if _askpass is None or not _askpass.exists():
            _askpass = create_askpass_script()
        git_env.set_ssh_env(build_git_env(credentials, _askpass))


def held() -> GitCredentials | None:
    """The credentials held now, or None."""
    with _lock:
        return _credentials


def release() -> None:
    """Forget the credentials, remove the askpass helper and unwire the git environment."""
    global _credentials, _askpass
    with _lock:
        _credentials = None
        if _askpass is not None:
            _askpass.unlink(missing_ok=True)
            _askpass = None
        git_env.set_ssh_env(None)


def supply(
    protocol: RemoteProtocol,
    *,
    secret: str,
    username: str | None,
    verify_against: Iterable[Path],
) -> None:
    """Add a credential for `protocol`, after checking the remotes that use it accept it.

    Each repository in `verify_against` whose origin is fetched or pushed over `protocol` is asked
    with the candidate credentials; a refusal raises `GitCredentialsRequired` with `rejected=True`
    naming that remote, and nothing is held. A remote that cannot be reached is not a refusal, so a
    network failure does not discard a correct passphrase.
    """
    current = held() or GitCredentials()
    candidate = current.with_ssh(secret) if protocol == "ssh" else current.with_https(username, secret)
    repos = [repo for repo in verify_against if repo.is_dir()]
    probe_askpass = create_askpass_script()
    try:
        failures = verify_credentials(
            repos, build_git_env(candidate, probe_askpass), protocols=frozenset({protocol})
        )
    finally:
        probe_askpass.unlink(missing_ok=True)
    if failures:
        refused_repo, _reason = failures[0]
        refused_url = next(
            (url for url in remote_urls(refused_repo) if protocol_of_url(url) == protocol), str(refused_repo)
        )
        raise GitCredentialsRequired(protocol=protocol, remote_url=refused_url, rejected=True)
    hold(candidate)
