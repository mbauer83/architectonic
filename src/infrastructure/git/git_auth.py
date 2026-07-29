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
import tempfile
from dataclasses import dataclass
from pathlib import Path


class GitCredentialError(RuntimeError):
    """The supplied git credentials are rejected by a configured remote and cannot be recovered
    interactively (they came from the environment / a non-interactive context). Raised so a wrong
    SSH passphrase / token fails loudly instead of the backend starting up as if sync were healthy
    and silently failing every poll."""


@dataclass
class GitCredentials:
    ssh_passphrase: str | None = None
    https_username: str | None = None
    https_password: str | None = None

    @property
    def has_ssh(self) -> bool:
        return bool(self.ssh_passphrase)

    @property
    def has_https(self) -> bool:
        return bool(self.https_username or self.https_password)


# ---------------------------------------------------------------------------
# Protocol detection
# ---------------------------------------------------------------------------


def detect_remote_protocol(repo_path: Path) -> str | None:
    """Return 'ssh', 'https', or None (local / no remote / repo not present yet)."""
    # A configured repo may not be cloned yet (arch-init runs before the backend in
    # real deployments, but not in every harness). Probing a missing path would make
    # subprocess.run raise FileNotFoundError on the cwd; treat it as "no remote".
    if not repo_path.is_dir():
        return None
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None
    return _protocol_from_url(result.stdout.strip())


def _protocol_from_url(url: str) -> str | None:
    if url.startswith(("git@", "ssh://", "git+ssh://")):
        return "ssh"
    if url.startswith(("https://", "http://")):
        return "https"
    return None


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

    Accepts either a local repo path or a bare remote URL (for arch-init pre-clone probing).
    Returns False on network timeout or non-auth errors so we don't over-prompt.
    """
    if isinstance(target, Path):
        cmd = ["git", "ls-remote", "--quiet", "--exit-code", "origin", "HEAD"]
        cwd = target
    else:
        cmd = ["git", "ls-remote", "--quiet", "--exit-code", str(target), "HEAD"]
        cwd = Path.cwd()

    try:
        result = subprocess.run(
            cmd,
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
    combined = (result.stdout + result.stderr).decode(errors="replace").lower()
    return any(p in combined for p in _AUTH_PHRASES)


# ---------------------------------------------------------------------------
# HTTPS credential resolution (supports a PAT supplied without a username)
# ---------------------------------------------------------------------------

# A non-empty username is required for HTTPS basic auth, but GitHub and GitLab ignore its
# value when the password is a token — so a PAT alone is enough. Hosts that *do* bind the
# username (e.g. Bitbucket app passwords) can still set ARCH_GIT_HTTPS_USERNAME explicitly.
_DEFAULT_TOKEN_USERNAME = "x-access-token"


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
        username = username or _DEFAULT_TOKEN_USERNAME
    return username, password


# ---------------------------------------------------------------------------
# Interactive collection
# ---------------------------------------------------------------------------


def collect_credentials(targets: list[Path | str]) -> GitCredentials | None:
    """Detect what credentials are needed and prompt interactively for any that are missing.

    Checks env-var overrides first; only prompts when on a TTY and probing confirms auth is needed.
    Returns None when no git remotes are found or no credentials are required.
    """
    ssh_targets = [t for t in targets if _target_protocol(t) == "ssh"]
    https_targets = [t for t in targets if _target_protocol(t) == "https"]

    if not ssh_targets and not https_targets:
        return None

    creds = GitCredentials()
    is_tty = sys.stdin.isatty()

    if ssh_targets:
        env_val = os.environ.get("ARCH_GIT_SSH_PASSWORD")
        if env_val:
            creds.ssh_passphrase = env_val
        elif is_tty and any(probe_needs_credential(t) for t in ssh_targets):
            creds.ssh_passphrase = getpass.getpass("SSH key passphrase: ")

    if https_targets:
        env_user, env_pass = resolve_https_from_env()
        if env_user or env_pass:
            creds.https_username = env_user
            creds.https_password = env_pass
        elif is_tty and any(probe_needs_credential(t) for t in https_targets):
            creds.https_username = input("Git username: ")
            creds.https_password = getpass.getpass("Git password/token: ")

    return creds if (creds.has_ssh or creds.has_https) else None


def _target_protocol(target: Path | str) -> str | None:
    if isinstance(target, str):
        return _protocol_from_url(target)
    return detect_remote_protocol(target)


# ---------------------------------------------------------------------------
# Credential verification (are the supplied credentials actually accepted?)
# ---------------------------------------------------------------------------


def _auth_rejection(target: Path, env: dict[str, str]) -> str | None:
    """Probe ``target``'s remote with the credential-wired ``env``. Returns the remote's message
    when it REJECTS the credentials (auth failure), else None — for a clean auth, a non-auth error
    (network), or a timeout. Only a genuine authentication rejection is reported, so a flaky
    network is never mistaken for a wrong passphrase."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--quiet", "--exit-code", "origin", "HEAD"],
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
    return combined if any(p in combined.lower() for p in _AUTH_PHRASES) else None


def verify_credentials(targets: list[Path], env: dict[str, str]) -> list[tuple[Path, str]]:
    """Verify that the supplied (credential-wired) ``env`` is actually accepted by each target's
    remote. Returns ``(path, reason)`` for every remote that rejects it — empty when all authenticate
    (or have no remote to check). Callers surface a non-empty result loudly rather than starting up
    as if sync were healthy."""
    failures: list[tuple[Path, str]] = []
    for target in targets:
        if detect_remote_protocol(target) is None:
            continue  # local / no remote — nothing to authenticate against
        reason = _auth_rejection(target, env)
        if reason is not None:
            failures.append((target, reason))
    return failures


def _has_env_credentials() -> bool:
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
            if not sys.stdin.isatty() or _has_env_credentials():
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


# ---------------------------------------------------------------------------
# Askpass env construction
# ---------------------------------------------------------------------------

# A PAT in ARCH_GIT_HTTPS_TOKEN stands in for the password, and defaults the username only
# when one isn't set — mirroring resolve_https_from_env() so a token alone authenticates
# even on a code path that hands git the raw process environment.
_ASKPASS_SCRIPT = (
    "#!/bin/sh\n"
    'prompt="${1:-}"\n'
    'case "$prompt" in\n'
    '  Username*) printf \'%s\\n\' "${ARCH_GIT_HTTPS_USERNAME:-${ARCH_GIT_HTTPS_TOKEN:+'
    + _DEFAULT_TOKEN_USERNAME + '}}" ;;\n'
    '  Password*) printf \'%s\\n\' "${ARCH_GIT_HTTPS_PASSWORD:-${ARCH_GIT_HTTPS_TOKEN:-}}" ;;\n'
    '  *)         printf \'%s\\n\' "${ARCH_GIT_SSH_PASSWORD:-}" ;;\n'
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
