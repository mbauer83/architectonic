"""The git credentials this process holds, and the askpass environment wired from them.

One owner for the credentials a running backend uses, and for the environment every git call reads
(`git_environment`). They arrive two ways: collected before startup (a terminal prompt or the
environment) and handed to `GitSyncManager`, or supplied later through the GUI when an operation was
refused for want of one. Both end here, so the askpass helper and the environment are built in one
place and read from one place: the write-queue executor's pushes (`_git_command`) and the background
sync's fetches run with the same credentials.

Held in memory for the process lifetime. Nothing here writes a credential to disk or to a log: the
askpass helper is a script that reads the secret from the environment of the git process it is
handed to, and `GitCredentials` keeps its secrets out of its `repr`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from pathlib import Path

from src.infrastructure.git.credential_refusal import GitCredentialsRequired
from src.infrastructure.git.git_auth import (
    GitCredentials,
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
#: The environment every git call runs with while credentials are held; None inherits the process's.
_environment: dict[str, str] | None = None


def hold(credentials: GitCredentials | None) -> None:
    """Hold `credentials` and wire every later git call to answer prompts from them.

    None holds nothing and leaves git with the process environment (an ssh-agent, a credential
    helper), which is what a workspace whose remotes need no credential runs with.
    """
    with _lock:
        _hold(credentials)


def _hold(credentials: GitCredentials | None) -> None:
    """`hold`, with the lock already taken."""
    global _credentials, _askpass, _environment
    _credentials = credentials
    if credentials is None or not (credentials.has_ssh or credentials.has_https):
        _environment = None
        return
    if _askpass is None or not _askpass.exists():
        _askpass = create_askpass_script()
    _environment = build_git_env(credentials, _askpass)


def held() -> GitCredentials | None:
    """The credentials held now, or None."""
    with _lock:
        return _credentials


def git_environment() -> dict[str, str] | None:
    """The environment a git call runs with: askpass wired from the held credentials, or None to inherit
    the process environment."""
    with _lock:
        return _environment


def release() -> None:
    """Forget the credentials, remove the askpass helper and unwire the git environment."""
    global _credentials, _askpass, _environment
    with _lock:
        _credentials = None
        _environment = None
        if _askpass is not None:
            _askpass.unlink(missing_ok=True)
            _askpass = None


def _with(base: GitCredentials | None, protocol: RemoteProtocol, secret: str, username: str | None) -> GitCredentials:
    """*base* (or nothing held) with *protocol*'s credential replaced, the other protocol's kept."""
    current = base or GitCredentials()
    return current.with_ssh(secret) if protocol == "ssh" else current.with_https(username, secret)


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

    The check runs without the lock (it reaches the network); what is held is read again under the lock
    before the verified credential is merged in, so a credential for the other protocol supplied
    meanwhile is kept rather than overwritten.
    """
    candidate = _with(held(), protocol, secret, username)
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
            (url for url in remote_urls(refused_repo).all if protocol_of_url(url) == protocol), str(refused_repo)
        )
        raise GitCredentialsRequired(protocol=protocol, remote_url=refused_url, rejected=True)
    with _lock:
        _hold(_with(_credentials, protocol, secret, username))
