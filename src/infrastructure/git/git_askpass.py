"""The askpass helper git and ssh ask for a credential, and the environment that wires it.

Split from `git_auth`, which collects credentials and reads remote URLs; this module only hands what was
collected to git. The helper answers an HTTPS username or password prompt only for an origin the
credential is bound to (`GitCredentials.https_origins`) and the key passphrase only to ssh's passphrase
prompt.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol


class GitCredentials(Protocol):
    """What the helper's environment is built from; `git_auth.GitCredentials` is the one that exists."""

    @property
    def ssh_passphrase(self) -> str | None: ...
    @property
    def https_username(self) -> str | None: ...
    @property
    def https_password(self) -> str | None: ...
    @property
    def https_origins(self) -> frozenset[str]: ...

#: The username a personal access token is sent with when none is configured; GitHub and GitLab ignore it.
DEFAULT_TOKEN_USERNAME = "x-access-token"


# A PAT in ARCH_GIT_HTTPS_TOKEN stands in for the password, and defaults the username only
# when one isn't set — mirroring resolve_https_from_env() so a token alone authenticates
# even on a code path that hands git the raw process environment.
#
# git names the origin in its prompt (`Password for 'https://user@host:8443': `); the helper answers
# only an origin listed in ARCH_GIT_CREDENTIAL_ORIGINS (see `GitCredentials.https_origins`) and
# gives the key passphrase only to ssh's own passphrase prompt — any other prompt (a password login
# to an ssh host, a host-key question) is answered with nothing.
_ASKPASS_SCRIPT = (
    "#!/bin/sh\n"
    'prompt="${1:-}"\n'
    'origin() { u=${1#*\\\'}; u=${u%%\\\'*}; s=${u%%://*}; r=${u#*://}; r=${r%%/*}; r=${r##*@}; '
    "printf '%s://%s' \"$s\" \"$r\" | tr 'A-Z' 'a-z'; }\n"
    'case "$prompt" in\n'
    '  Username*|Password*)\n'
    '    case " ${ARCH_GIT_CREDENTIAL_ORIGINS:-} " in\n'
    '      *" $(origin "$prompt") "*) ;;\n'
    "      *) printf '\\n'; exit 0 ;;\n"
    "    esac ;;\n"
    "esac\n"
    'case "$prompt" in\n'
    '  Username*) printf \'%s\\n\' "${ARCH_GIT_HTTPS_USERNAME:-${ARCH_GIT_HTTPS_TOKEN:+'
    + DEFAULT_TOKEN_USERNAME + '}}" ;;\n'
    '  Password*) printf \'%s\\n\' "${ARCH_GIT_HTTPS_PASSWORD:-${ARCH_GIT_HTTPS_TOKEN:-}}" ;;\n'
    '  "Enter passphrase"*) printf \'%s\\n\' "${ARCH_GIT_SSH_PASSWORD:-}" ;;\n'
    "  *) printf '\\n' ;;\n"
    "esac\n"
)


def create_askpass_script() -> Path:
    """Write the shared askpass helper to a tempfile and return its path."""
    fd, path_str = tempfile.mkstemp(prefix="arch-askpass-", suffix=".sh")
    path = Path(path_str)
    try:
        os.write(fd, _ASKPASS_SCRIPT.encode())
    finally:
        os.close(fd)
    path.chmod(0o700)
    return path


def build_git_env(credentials: GitCredentials, askpass: Path) -> dict[str, str]:
    """Return a git subprocess environment with askpass wired for SSH and HTTPS."""
    env = os.environ.copy()
    env["SSH_ASKPASS"] = str(askpass)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    env["GIT_ASKPASS"] = str(askpass)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["ARCH_GIT_SSH_PASSWORD"] = credentials.ssh_passphrase or ""
    env["ARCH_GIT_HTTPS_USERNAME"] = credentials.https_username or ""
    env["ARCH_GIT_HTTPS_PASSWORD"] = credentials.https_password or ""
    env["ARCH_GIT_CREDENTIAL_ORIGINS"] = " ".join(sorted(credentials.https_origins))
    return env


# ---------------------------------------------------------------------------
# Daemon credential handoff
# ---------------------------------------------------------------------------


def credentials_to_env_overrides(credentials: GitCredentials | None) -> dict[str, str]:
    """Return env-var overrides to set before spawning a daemon so it inherits credentials."""
    if credentials is None:
        return {}
    result: dict[str, str] = {}
    if credentials.ssh_passphrase:
        result["ARCH_GIT_SSH_PASSWORD"] = credentials.ssh_passphrase
    # When the HTTPS secret comes from a token file, the daemon already inherits the file
    # path (ARCH_GIT_HTTPS_TOKEN_FILE) and re-reads it, so we don't expand the token value
    # into the daemon's environment.
    if not os.environ.get("ARCH_GIT_HTTPS_TOKEN_FILE"):
        if credentials.https_username:
            result["ARCH_GIT_HTTPS_USERNAME"] = credentials.https_username
        if credentials.https_password:
            result["ARCH_GIT_HTTPS_PASSWORD"] = credentials.https_password
    return result
