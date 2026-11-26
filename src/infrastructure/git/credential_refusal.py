"""A remote's refusal for want of a credential: recognising it, and saying it without the secret.

Separate from `git_auth`, which collects and wires credentials, because this is the other direction:
reading a failed command's output as "a credential is needed" (or "the one held was refused") and
naming the protocol and remote it was for. Every operation that reaches `origin` reports a refusal
through here (`_git_command.refuse_for_missing_credentials`), and REST and MCP both read the result.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from src.infrastructure.git.git_auth import (
    GitCredentials,
    RemoteProtocol,
    is_authentication_failure,
    protocol_of_url,
    remote_urls,
)


class GitCredentialsRequired(RuntimeError):
    """A git command that reaches a remote was refused for want of a credential.

    Raised in place of the plain failure so a caller can ask for the credential instead of
    reporting a push that failed. A `RuntimeError`, so every caller that already reports a failed
    push keeps doing so with this message. The message and fields name the protocol and the remote
    (with any userinfo removed) and never a secret.
    """

    def __init__(self, *, protocol: RemoteProtocol, remote_url: str, rejected: bool) -> None:
        self.protocol: RemoteProtocol = protocol
        self.remote_url = redact_url(remote_url)
        #: True when a credential for this protocol was held and the remote refused it anyway.
        self.rejected = rejected
        what = "SSH key passphrase" if protocol == "ssh" else "HTTPS username and token"
        state = "was refused" if rejected else "is needed"
        super().__init__(
            f"The {what} for origin ({self.remote_url}) {state}. Enter it when the GUI asks, or set "
            f"{_ENVIRONMENT_HINT[protocol]} and restart the backend. Secrets are not accepted over MCP."
        )


_ENVIRONMENT_HINT: dict[RemoteProtocol, str] = {
    "ssh": "ARCH_GIT_SSH_PASSWORD (or load the key into ssh-agent)",
    "https": "ARCH_GIT_HTTPS_TOKEN",
}


def redact_url(url: str) -> str:
    """`url` without the userinfo of a URL-form remote, where a token can be embedded."""
    if "://" not in url:
        return url  # scp-like `user@host:path` carries a login name, never a secret
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def credentials_required_for(
    repo: Path, *, pushing: bool, git_output: str, held: GitCredentials | None
) -> GitCredentialsRequired | None:
    """The refusal a failed remote command amounts to, or None when it failed for another reason.

    Which URL was used follows from the direction: a push goes to the push URL, everything else to
    the fetch URL. Where a remote has push URLs of both protocols, git's own wording decides — ssh
    names the key it tried, https the URL it asked a username for.
    """
    if not is_authentication_failure(git_output):
        return None
    urls = remote_urls(repo)
    if not urls:
        return None
    # `remote_urls` is the fetch URL followed by the push URLs that differ from it.
    candidates = (urls[1:] or urls[:1]) if pushing else urls[:1]
    by_protocol = {p: url for url in candidates if (p := protocol_of_url(url)) is not None}
    if not by_protocol:
        return None
    protocol: RemoteProtocol
    if len(by_protocol) == 1:
        protocol = next(iter(by_protocol))
    else:
        protocol = "https" if "http" in git_output.lower() else "ssh"
    return GitCredentialsRequired(
        protocol=protocol,
        remote_url=by_protocol[protocol],
        rejected=held is not None and held.holds(protocol),
    )
