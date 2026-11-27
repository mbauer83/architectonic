"""Git authentication: credential detection, interactive prompts, and askpass env setup.

Handles SSH key passphrases (via SSH_ASKPASS) and HTTPS username/password (via GIT_ASKPASS).
Credentials are never written to disk; they live in memory for the process lifetime.

CI / non-interactive overrides (skips prompting):
  ARCH_GIT_SSH_PASSWORD   — SSH key passphrase
  ARCH_GIT_HTTPS_USERNAME — HTTPS username
  ARCH_GIT_HTTPS_PASSWORD — HTTPS password or token
  ARCH_GIT_HTTPS_TOKEN    — personal access token; used as the password when no explicit
                            password is given, defaulting the username so a PAT alone is
                            sufficient (GitHub/GitLab ignore the username for token auth).
  ARCH_GIT_HTTPS_TOKEN_FILE — path to a file holding the PAT (docker/k8s secret, or the
                            `--git-token-file` CLI flag). Read when the inline token is unset.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from src.infrastructure.git.git_askpass import (
    DEFAULT_TOKEN_USERNAME,
    build_git_env,
    create_askpass_script,
)

#: The protocols this module supplies a credential for.
RemoteProtocol = Literal["ssh", "https"]


class GitCredentialError(RuntimeError):
    """The supplied git credentials are rejected by a configured remote and cannot be recovered
    interactively (they came from the environment / a non-interactive context). Raised so a wrong
    SSH passphrase / token fails loudly instead of the backend starting up as if sync were healthy
    and silently failing every poll."""


@dataclass
class GitCredentials:
    # `repr=False` on every secret: a dataclass prints its fields, and a credential object that
    # reaches a log line or a traceback must not carry its value there.
    ssh_passphrase: str | None = field(default=None, repr=False)
    https_username: str | None = None
    https_password: str | None = field(default=None, repr=False)
    #: The origins (`scheme://host[:port]`) the HTTPS credential was collected or verified for. The
    #: askpass helper answers a username or password prompt only from one of these, so a redirect, a
    #: submodule or another remote never receives the token — nor a plain-http origin an https one.
    https_origins: frozenset[str] = frozenset()

    @property
    def has_ssh(self) -> bool:
        return bool(self.ssh_passphrase)

    @property
    def has_https(self) -> bool:
        return bool(self.https_username or self.https_password)

    def holds(self, protocol: RemoteProtocol) -> bool:
        return self.has_ssh if protocol == "ssh" else self.has_https

    def with_ssh(self, passphrase: str) -> GitCredentials:
        return replace(self, ssh_passphrase=passphrase)

    def with_https(self, username: str | None, password: str) -> GitCredentials:
        return replace(self, https_username=username or DEFAULT_TOKEN_USERNAME, https_password=password)

    def for_origins(self, urls: Iterable[str]) -> GitCredentials:
        """These credentials, with the HTTPS credential also bound to the origins of *urls*."""
        return replace(self, https_origins=self.https_origins | credential_origins(urls))


# ---------------------------------------------------------------------------
# Protocol detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RemoteUrls:
    """Where git reaches `origin`: the fetch URL, and the URLs a push goes to (each once)."""

    fetch: str | None
    push: tuple[str, ...] = ()

    @property
    def all(self) -> tuple[str, ...]:
        """Every URL `origin` is fetched or pushed by: the fetch URL, then each push URL, without repeats."""
        return tuple(dict.fromkeys(url for url in (self.fetch, *self.push) if url))

    @property
    def pushed_to(self) -> tuple[str, ...]:
        """The URLs a push goes to; the fetch URL where no push URL is reported."""
        return self.push or ((self.fetch,) if self.fetch else ())


def remote_urls(repo_path: Path) -> RemoteUrls:
    """Every URL git reaches `origin` by, the fetch URL apart from the push URLs.

    Asked of git rather than read from `.git/config`, because git is what decides: `pushurl`,
    `pushInsteadOf` and `insteadOf` all change where a push goes without changing the fetch URL. A
    remote that fetches over https and pushes over ssh needs both protocols' credentials, and reading
    only the fetch URL is how a push came to run with no askpass at all.
    """
    # A configured repo may not be cloned yet (arch-init runs before the backend in real
    # deployments, but not in every harness). Probing a missing path would make
    # subprocess.run raise FileNotFoundError on the cwd; treat it as "no remote".
    if not repo_path.is_dir():
        return RemoteUrls(None)
    fetch = _git_remote_lines(repo_path, ("get-url", "origin"))
    push = _git_remote_lines(repo_path, ("get-url", "--push", "--all", "origin"))
    return RemoteUrls(fetch[0] if fetch else None, tuple(dict.fromkeys(push)))


def _git_remote_lines(repo_path: Path, query: tuple[str, ...]) -> list[str]:
    result = subprocess.run(["git", "remote", *query], cwd=repo_path, capture_output=True, text=True, timeout=5)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()] if result.returncode == 0 else []


def detect_remote_protocols(repo_path: Path) -> frozenset[RemoteProtocol]:
    """The protocols ('ssh', 'https') `origin` is fetched or pushed over; empty for none or local."""
    return frozenset(p for p in (protocol_of_url(url) for url in remote_urls(repo_path).all) if p)


# ---------------------------------------------------------------------------
# Reading a remote URL — the one reader of the forms git accepts for a remote
# ---------------------------------------------------------------------------

#: The URL schemes a credential is supplied for, by the protocol that supplies it.
_SCHEMES: dict[str, RemoteProtocol] = {"ssh": "ssh", "git+ssh": "ssh", "https": "https", "http": "https"}


@dataclass(frozen=True)
class RemoteUrl:
    """A remote URL read once: the protocol a credential is supplied for, the host, the repository path."""

    text: str
    protocol: RemoteProtocol
    host: str
    path: str


def read_remote_url(url: str) -> RemoteUrl | None:
    """*url* read as a remote reached over ssh or https, in URL form or scp form (`user@host:path`,
    `host-alias:path`); None for a local path (a drive letter is a one-letter "host"), `file://`, `git://`
    and the rest, which need no credential this module supplies."""
    if "://" in url:
        parts = urlsplit(url)
        protocol = _SCHEMES.get(parts.scheme)
        return RemoteUrl(url, protocol, parts.hostname.lower(), parts.path) if protocol and parts.hostname else None
    head, colon, path = url.partition(":")
    host = head.rpartition("@")[2]
    if not colon or "/" in head or len(head) < 2 or not host:
        return None
    return RemoteUrl(url, "ssh", host.lower(), path)


def credential_origins(urls: Iterable[str]) -> frozenset[str]:
    """The `scheme://host[:port]` of each URL-form remote in *urls* that takes an HTTPS credential —
    what git names in its credential prompt, so the askpass helper can compare the two."""
    found = (urlsplit(url) for url in urls if "://" in url and protocol_of_url(url) == "https")
    return frozenset(
        f"{parts.scheme}://{parts.hostname}" + (f":{parts.port}" if parts.port else "")
        for parts in found
        if parts.hostname
    )


def protocol_of_url(url: str) -> RemoteProtocol | None:
    """The protocol a remote URL needs a credential for, or None for a local or anonymous one."""
    read = read_remote_url(url)
    return read.protocol if read is not None else None


def redacted_url(url: str) -> str:
    """*url* without the userinfo of a URL-form remote, where a token can be embedded. The scp form
    (`user@host:path`) carries a login name, never a secret, and is left as it is."""
    if "://" not in url:
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _target_urls(target: Path | str) -> tuple[str, ...]:
    return (target,) if isinstance(target, str) else remote_urls(target).all


def _urls_over(targets: list[Path | str], protocol: str) -> list[tuple[Path | str, str]]:
    """Each (target, url) pair whose url uses `protocol`."""
    return [
        (target, url) for target in targets for url in _target_urls(target) if protocol_of_url(url) == protocol
    ]


# ---------------------------------------------------------------------------
# Credential probing
# ---------------------------------------------------------------------------

_NO_ASKPASS = "/bin/false"
_AUTH_PHRASES = (
    "permission denied",
    "passphrase",
    "bad permissions",
    "authentication failed",
    "could not read username",
    "authorization failed",
    "403",
    "invalid username or password",
)


def probe_needs_credential(target: Path | str) -> bool:
    """Return True when git ls-remote fails specifically due to missing authentication.

    Accepts either a local repo path — every URL its `origin` is fetched or pushed over is probed —
    or a bare remote URL (for arch-init pre-clone probing). Returns False on network timeout or
    non-auth errors so we don't over-prompt.
    """
    cwd = target if isinstance(target, Path) else Path.cwd()
    return any(_probe_url_needs_credential(url, cwd) for url in _target_urls(target))


def _probe_url_needs_credential(url: str, cwd: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--quiet", "--exit-code", url, "HEAD"],
            cwd=cwd,
            capture_output=True,
            env={
                **os.environ,
                "SSH_ASKPASS": _NO_ASKPASS,
                "SSH_ASKPASS_REQUIRE": "force",
                "GIT_ASKPASS": _NO_ASKPASS,
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        return False

    if result.returncode == 0:
        return False
    return is_authentication_failure((result.stdout + result.stderr).decode(errors="replace"))


def is_authentication_failure(git_output: str) -> bool:
    """Whether git's output says a remote refused for want of a credential, not for another reason."""
    lowered = git_output.lower()
    return any(p in lowered for p in _AUTH_PHRASES)


# ---------------------------------------------------------------------------
# HTTPS credential resolution (supports a PAT supplied without a username)
# ---------------------------------------------------------------------------

# A non-empty username is required for HTTPS basic auth, but GitHub and GitLab ignore its
# value when the password is a token — so a PAT alone is enough. Hosts that *do* bind the
# username (e.g. Bitbucket app passwords) can still set ARCH_GIT_HTTPS_USERNAME explicitly.


def _read_secret_file(env_var: str) -> str | None:
    """Read a secret from the file path held in *env_var* (trailing whitespace stripped)."""
    path = os.environ.get(env_var)
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def register_token_file(path: str | None) -> None:
    """Wire a ``--git-token-file`` CLI value into the shared, env-based resolver.

    Sets the *path* (not the token) in the environment so a spawned daemon inherits only the
    location and re-reads the file itself — the secret never enters the operator-facing config.
    """
    if path:
        os.environ["ARCH_GIT_HTTPS_TOKEN_FILE"] = path


def resolve_https_from_env() -> tuple[str | None, str | None]:
    """Resolve the effective (username, password) for HTTPS auth from the environment.

    ``ARCH_GIT_HTTPS_TOKEN`` (inline) or ``ARCH_GIT_HTTPS_TOKEN_FILE`` (a file path, e.g. a
    docker/k8s secret or ``--git-token-file``) is a personal access token: it becomes the
    password when no explicit ``ARCH_GIT_HTTPS_PASSWORD`` is set, and supplies a default
    username when none is given. Explicit username/password always take precedence.
    """
    username = os.environ.get("ARCH_GIT_HTTPS_USERNAME") or None
    password = os.environ.get("ARCH_GIT_HTTPS_PASSWORD") or None
    token = os.environ.get("ARCH_GIT_HTTPS_TOKEN") or _read_secret_file("ARCH_GIT_HTTPS_TOKEN_FILE")
    if token and not password:
        password = token
        username = username or DEFAULT_TOKEN_USERNAME
    return username, password


# ---------------------------------------------------------------------------
# Interactive collection
# ---------------------------------------------------------------------------


def collect_credentials(targets: list[Path | str]) -> GitCredentials | None:
    """Detect what credentials are needed and prompt interactively for any that are missing.

    Checks env-var overrides first; only prompts when on a TTY and probing confirms auth is needed.
    Returns None when no git remotes are found or no credentials are required.
    """
    ssh_urls = _urls_over(targets, "ssh")
    https_urls = _urls_over(targets, "https")

    if not ssh_urls and not https_urls:
        return None

    creds = GitCredentials()
    is_tty = sys.stdin.isatty()

    if ssh_urls:
        env_val = os.environ.get("ARCH_GIT_SSH_PASSWORD")
        if env_val:
            creds.ssh_passphrase = env_val
        elif is_tty and any(_probe_url_needs_credential(url, _cwd_of(t)) for t, url in ssh_urls):
            creds.ssh_passphrase = getpass.getpass("SSH key passphrase: ")

    if https_urls:
        env_user, env_pass = resolve_https_from_env()
        if env_user or env_pass:
            creds.https_username = env_user
            creds.https_password = env_pass
        elif is_tty and any(_probe_url_needs_credential(url, _cwd_of(t)) for t, url in https_urls):
            creds.https_username = input("Git username: ")
            creds.https_password = getpass.getpass("Git password/token: ")
        creds = creds.for_origins(url for _, url in https_urls)

    return creds if (creds.has_ssh or creds.has_https) else None


def _cwd_of(target: Path | str) -> Path:
    return target if isinstance(target, Path) else Path.cwd()


# ---------------------------------------------------------------------------
# Credential verification (are the supplied credentials actually accepted?)
# ---------------------------------------------------------------------------


def _auth_rejection(target: Path, url: str, env: dict[str, str]) -> str | None:
    """Probe `url` from ``target`` with the credential-wired ``env``. Returns the remote's message
    when it REJECTS the credentials (auth failure), else None — for a clean auth, a non-auth error
    (network), or a timeout. Only a genuine authentication rejection is reported, so a flaky
    network is never mistaken for a wrong passphrase."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--quiet", "--exit-code", url, "HEAD"],
            cwd=target,
            capture_output=True,
            env=env,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode == 0:
        return None
    combined = (result.stdout + result.stderr).decode(errors="replace").strip()
    return combined if is_authentication_failure(combined) else None


def verify_credentials(
    targets: list[Path], env: dict[str, str], *, protocols: frozenset[str] = frozenset({"ssh", "https"})
) -> list[tuple[Path, str]]:
    """Verify that the supplied (credential-wired) ``env`` is actually accepted by each target's
    remote, over every URL it is fetched or pushed by whose protocol is in ``protocols``. Returns
    ``(path, reason)`` for every remote that rejects it — empty when all authenticate (or have no
    remote to check). Callers surface a non-empty result loudly rather than starting up as if sync
    were healthy."""
    failures: list[tuple[Path, str]] = []
    for target in targets:
        for url in remote_urls(target).all:
            if protocol_of_url(url) not in protocols:
                continue  # local / no remote, or a protocol this check is not about
            reason = _auth_rejection(target, url, env)
            if reason is not None:
                failures.append((target, reason))
                break
    return failures


def has_env_credentials() -> bool:
    """True when git credentials come from the environment (so a rejection can't be re-prompted)."""
    if os.environ.get("ARCH_GIT_SSH_PASSWORD"):
        return True
    username, password = resolve_https_from_env()
    return bool(username or password)


def collect_verified_credentials(targets: list[Path | str]) -> GitCredentials | None:
    """Collect git credentials and VERIFY they are accepted before returning them.

    On a rejection: when the credentials were entered at a TTY (not from the environment), print
    that they were invalid and re-prompt — looping until they authenticate or the operator aborts
    (Ctrl-C raises KeyboardInterrupt). When they came from the environment / a non-interactive
    context (a re-prompt can't fix that), raise :class:`GitCredentialError` so startup fails loudly.
    """
    creds = collect_credentials(targets)
    if creds is None:
        return None
    paths = [t for t in targets if isinstance(t, Path)]
    if not paths:
        return creds  # only bare-URL targets (pre-clone) — no local remote to verify against
    askpass = create_askpass_script()
    try:
        while True:
            failures = verify_credentials(paths, build_git_env(creds, askpass))
            if not failures:
                return creds
            reason = "; ".join(f"{path}: {r}" for path, r in failures)
            if not sys.stdin.isatty() or has_env_credentials():
                raise GitCredentialError(
                    f"Git authentication was rejected with the supplied credentials ({reason}). "
                    "Fix the credentials and restart."
                )
            print(
                f"\nGit authentication was rejected ({reason}).\n"
                "Please re-enter your credentials (Ctrl-C to abort).",
                file=sys.stderr,
            )
            reprompted = collect_credentials(targets)
            if reprompted is None or not (reprompted.has_ssh or reprompted.has_https):
                raise GitCredentialError(f"Git authentication was rejected ({reason}).")
            creds = reprompted
    finally:
        askpass.unlink(missing_ok=True)
