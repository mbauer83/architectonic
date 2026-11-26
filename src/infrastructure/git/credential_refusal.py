"""A remote's refusal for want of a credential: recognising it, and saying it without the secret.

Separate from `git_auth`, which collects and wires credentials, because this is the other direction:
reading a failed command's output as "a credential is needed" (or "the one held was refused") and
naming the protocol and remote it was for. Every git command that reaches `origin` runs through the
remote runners in `_git_command`, which raise the refusal from here; REST and MCP each map it once.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.git.git_auth import (
    GitCredentials,
    RemoteProtocol,
    is_authentication_failure,
    protocol_of_url,
    redacted_url,
    remote_urls,
)


class GitCredentialsRequired(Exception):
    """A git command that reaches a remote was refused for want of a credential.

    Raised in place of the plain failure so a caller can ask for the credential instead of reporting a
    failed push. Deliberately not a `RuntimeError`: a caller that reports other failures of the same
    operation as its own error does not fold this one in with them, so it reaches the transport's one
    mapping (`git_credentials_required` over REST, the MCP tools' refusal) wherever it arises.

    The message names the protocol and the remote (with any userinfo removed) and never a secret, and says
    nothing about which transport is asking: each adds its own remedy, and `environment_hint` names what
    every one of them can point to — where the credential is read from without anyone being asked.
    """

    def __init__(self, *, protocol: RemoteProtocol, remote_url: str, rejected: bool) -> None:
        self.protocol: RemoteProtocol = protocol
        self.remote_url = redacted_url(remote_url)
        #: True when a credential for this protocol was held and the remote refused it anyway.
        self.rejected = rejected
        what = "SSH key passphrase" if protocol == "ssh" else "HTTPS username and token"
        state = "was refused" if rejected else "is needed"
        super().__init__(f"The {what} for origin ({self.remote_url}) {state}.")

    @property
    def environment_hint(self) -> str:
        """Where this credential is read from without a prompt: the environment variable (or the agent)."""
        return _ENVIRONMENT_HINT[self.protocol]


_ENVIRONMENT_HINT: dict[RemoteProtocol, str] = {
    "ssh": "ARCH_GIT_SSH_PASSWORD (or load the key into ssh-agent)",
    "https": "ARCH_GIT_HTTPS_TOKEN",
}


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
    candidates = urls.pushed_to if pushing else urls.all[:1]
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
