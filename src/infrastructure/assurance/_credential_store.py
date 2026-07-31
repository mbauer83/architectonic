"""Secure credential storage for arch-assurance encryption keys.

Backend selection order:
  1. macOS Keychain        — macOS; always available and secure
  2. Windows DPAPI bridge  — WSL2; powershell.exe Export-Clixml (DPAPI-encrypted,
                             tied to Windows user login; cannot be decrypted by any
                             other user or on any other machine)
  3. SecretService D-Bus   — native Linux with a running desktop session
  4. Fernet-encrypted vault — headless Linux / CI; requires ARCH_ASSURANCE_MASTER_PASSWORD
                             env var; AES-128-CBC via PBKDF2-derived key

Fails loudly with actionable instructions if no secure backend is available.
Never falls back to plaintext storage.
"""

from __future__ import annotations

import logging
import os
import platform
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class CredentialUnavailable(RuntimeError):
    """The credential could not be read — as distinct from not existing.

    The distinction is the whole reason this exists. A caller deciding what to do about a *missing*
    credential (initialise a store, fall back to a legacy account, prompt an operator) must never make
    that decision because a keychain was slow. Both used to arrive as ``None``.
    """


@runtime_checkable
class _Backend(Protocol):
    def get(self, account: str) -> str | None:
        """The value, or ``None`` only if the credential does not exist.

        Raises ``CredentialUnavailable`` when it exists and cannot be read. Every implementation owes
        the caller this distinction; returning ``None`` for a failure is the defect that cost a store.
        """
        ...

    def set(self, account: str, value: str) -> None: ...
    def delete(self, account: str) -> None: ...

_SERVICE = "arch-assurance"
_MASTER_PW_ENV = "ARCH_ASSURANCE_MASTER_PASSWORD"
_CREDENTIALS_DIR_ENV = "ARCH_ASSURANCE_CREDENTIALS_DIR"


def _config_dir() -> Path:
    """Resolve the credential directory at USE time, honouring the env override.

    The override exists so the test suite (and anything it spawns — subprocesses
    inherit the environment) physically cannot reach a developer's real
    ``~/.config/arch-assurance``. Two guards have failed before by protecting only
    backend *selection* inside one process; redirecting the directory itself makes
    the whole class of accidents land in a throwaway tmp dir instead.
    """
    override = os.environ.get(_CREDENTIALS_DIR_ENV)
    return Path(override) if override else Path.home() / ".config" / "arch-assurance"

#: Set by the test suite. While it is set, no real credential backend may EVER be selected.
#:
#: INCIDENT (2026-07-20, again 2026-07-28): a test reached the real OS credential backend and
#: overwrote the live store's `db-encryption-key`, leaving the developer's encrypted store
#: permanently unopenable — the ciphertext survives, the key does not.
#:
#: The first guard installed an in-memory backend over the module global (`tests/conftest.py`).
#: That was necessary and insufficient: `reset_backend()` nulls the same global, and the next
#: `_get_backend()` re-selects a real backend. Any test that legitimately exercises backend
#: selection therefore silently re-armed the hazard for every test that ran after it.
#:
#: This gate fails closed instead of relying on a value that something else may clear: while
#: the variable is set, selection raises rather than reaching a keychain. A test that wants a
#: working credential store installs its own fake — an explicit act — and one that reaches for
#: the real thing gets a loud error instead of destroying a developer's data.
_FORBID_REAL_BACKEND_ENV = "ARCH_ASSURANCE_FORBID_REAL_CREDENTIAL_BACKEND"

_FORBIDDEN_MSG = (
    "Refusing to select a real OS credential backend: "
    f"{_FORBID_REAL_BACKEND_ENV} is set, which the test suite does to make it impossible to "
    "overwrite a developer's live assurance-store key. Install an explicit in-memory backend "
    "for this test (see tests/conftest.py) rather than unsetting this variable."
)

_NO_BACKEND_MSG = (
    "No secure credential backend is available for arch-assurance.\n\n"
    "  macOS:                    automatic (Keychain)\n"
    "  WSL2:                     automatic (Windows DPAPI); ensure Windows\n"
    "                            PowerShell interop is enabled\n"
    "  Linux desktop (D-Bus):    automatic (SecretService / gnome-keyring)\n"
    "  Headless Linux / CI:      set ARCH_ASSURANCE_MASTER_PASSWORD env var\n"
    "                            (add to ~/.bashrc or systemd unit)\n"
)


# ── keyring-backed (macOS Keychain + SecretService) ───────────────────────────


class _KeyringBackend:
    """Thin wrapper around a specific `keyring` backend class."""

    def __init__(self, backend_module: str, backend_class: str) -> None:
        import importlib  # noqa: PLC0415

        cls = getattr(importlib.import_module(backend_module), backend_class)
        self._kr = cls()

    def get(self, account: str) -> str | None:
        """``None`` only when the keychain holds no such account.

        ``keyring`` raises for a locked or unavailable backend, and that must stay an error: a locked
        Keychain reported as "no credential" reads as an unconfigured store.
        """
        try:
            return self._kr.get_password(_SERVICE, account)
        except Exception as exc:
            raise CredentialUnavailable(
                f"Could not read credential {account!r} from the OS keychain: {type(exc).__name__}."
            ) from exc

    def set(self, account: str, value: str) -> None:
        self._kr.set_password(_SERVICE, account, value)

    def delete(self, account: str) -> None:
        try:
            self._kr.delete_password(_SERVICE, account)
        except Exception:  # noqa: BLE001
            pass


# ── Windows DPAPI via PowerShell bridge (WSL2) ────────────────────────────────


class _DPAPIBackend:
    """Each credential stored as a DPAPI-encrypted PSCredential XML file.

    PowerShell Export-Clixml serialises PSCredential with the password
    encrypted by Windows DPAPI (user-and-machine-scoped). Files live on the
    WSL2 filesystem; wslpath converts them to Windows UNC paths for PowerShell.
    """

    @property
    def _creds(self) -> Path:
        return _config_dir() / "creds"

    def _path(self, account: str) -> Path:
        return self._creds / f"{account.replace('-', '_')}.clixml"

    @staticmethod
    def _win(path: Path) -> str:
        import subprocess  # noqa: PLC0415
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()

    def get(self, account: str) -> str | None:
        """The stored value, ``None`` only when this credential does not exist.

        A failure to read raises. It used to return ``None``, which made "the keychain could not
        answer" indistinguishable from "there is no such credential" — and on WSL2 every read is a
        ``powershell.exe`` spawn that can time out under load. A caller that treats absence as a
        migration cue then acts on a false absence, which is how the live store's key was replaced by
        a stale one on 2026-07-31. Absence is a fact about the store; a timeout is a fact about the
        machine, and no caller can tell them apart once they are the same value.
        """
        import subprocess  # noqa: PLC0415
        p = self._path(account)
        if not p.exists():
            return None
        try:
            out = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"(Import-Clixml '{self._win(p)}').GetNetworkCredential().Password"],
                text=True, timeout=15,
            )
        except Exception as exc:
            raise CredentialUnavailable(
                f"Could not read credential {account!r}: {type(exc).__name__}. The credential exists "
                "on disk; this is a failure to read it, not an absence. Retry once the machine is "
                "less loaded — treating this as 'not configured' is how a live key gets replaced."
            ) from exc
        # An existing file that decrypts to nothing is a damaged credential, not an absent one:
        # reporting it as absent would invite the same false-absence handling.
        value = out.strip()
        if not value:
            raise CredentialUnavailable(
                f"Credential {account!r} exists but decrypted to an empty value — it is damaged."
            )
        return value

    def set(self, account: str, value: str) -> None:
        """Write one credential, replacing any existing file — including a read-only one.

        The re-protect step below is why this needs care. Credential files are chmod-protected
        after every write, and `Export-Clixml` cannot overwrite a read-only file: PowerShell exits
        1, and with `capture_output` that surfaced as a bare `CalledProcessError` naming the whole
        command and no reason. So the store made itself unwritable and reported it as an unhelpful
        subprocess failure — which is what stopped `arch-assurance unlock`, since unlock rewrites
        the setup gate on every run.

        The protection is deliberate (it exists because keys have been lost), so it is restored
        rather than dropped: the file's own mode is read first, relaxed for the write, and put back.
        """
        import subprocess  # noqa: PLC0415
        self._creds.mkdir(parents=True, exist_ok=True)
        os.chmod(self._creds, 0o700)
        p = self._path(account)
        # Whatever protection this file already carries is the protection it gets back. A file
        # hardened to 0400 out of band must not be quietly loosened to 0600 by a rewrite.
        restore_mode = stat.S_IMODE(p.stat().st_mode) if p.exists() else 0o600
        if p.exists():
            os.chmod(p, 0o600)
        esc = value.replace("'", "''")
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"[PSCredential]::new('arch-assurance',"
                 f"(ConvertTo-SecureString '{esc}' -AsPlainText -Force))"
                 f" | Export-Clixml '{self._win(p)}'"],
                check=False, timeout=15, capture_output=True, text=True,
            )
        finally:
            # In `finally`, because a write that did not happen must not leave the file relaxed. The
            # relaxation is a means to one write, never a state the file is left in.
            if p.exists():
                os.chmod(p, restore_mode)
        if completed.returncode != 0:
            # The command line carries the credential value, so it is not echoed. PowerShell's own
            # stderr is — a failure with no reason is what made this take a debugging session.
            raise RuntimeError(
                f"Could not write the credential for {account!r} to {p}: PowerShell exited "
                f"{completed.returncode}. {(completed.stderr or '').strip() or 'No error output.'}"
            )

    def delete(self, account: str) -> None:
        p = self._path(account)
        if p.exists():
            p.unlink()


# ── Fernet-encrypted vault (headless Linux / CI) ──────────────────────────────


class _FernetVault:
    """All credentials in one Fernet-encrypted JSON file, key from PBKDF2."""

    _ITERATIONS = 480_000

    @property
    def _vault(self) -> Path:
        return _config_dir() / "vault.enc"

    def __init__(self, master_password: str) -> None:
        self._pw = master_password

    def _fernet(self, salt: bytes) -> Fernet:
        import base64  # noqa: PLC0415

        from cryptography.fernet import Fernet  # noqa: PLC0415
        from cryptography.hazmat.primitives import hashes  # noqa: PLC0415
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # noqa: PLC0415
        key = base64.urlsafe_b64encode(
            PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                       iterations=self._ITERATIONS).derive(self._pw.encode())
        )
        return Fernet(key)

    def _load(self) -> dict[str, str]:
        import base64  # noqa: PLC0415
        import json  # noqa: PLC0415

        if not self._vault.exists():
            return {}
        raw = json.loads(self._vault.read_text())
        return json.loads(
            self._fernet(base64.b64decode(raw["salt"])).decrypt(
                base64.b64decode(raw["data"])
            )
        )

    def _save(self, entries: dict[str, str]) -> None:
        import base64  # noqa: PLC0415
        import json  # noqa: PLC0415
        salt = os.urandom(16)
        data = self._fernet(salt).encrypt(json.dumps(entries).encode())
        self._vault.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._vault.parent, 0o700)
        self._vault.write_text(json.dumps({
            "v": 1,
            "salt": base64.b64encode(salt).decode(),
            "data": base64.b64encode(data).decode(),
        }))
        os.chmod(self._vault, 0o600)

    def get(self, account: str) -> str | None:
        """``None`` only for an account this vault does not hold.

        A vault that exists and will not decrypt — wrong master password, truncated file — raises,
        because every account in it is then unreadable rather than absent. Reporting "absent" would
        tell a caller the store was never configured.
        """
        try:
            entries = self._load()
        except Exception as exc:
            raise CredentialUnavailable(
                f"Could not open the credential vault at {self._vault}: {type(exc).__name__}. "
                "Its accounts are unreadable, not absent."
            ) from exc
        return entries.get(account)

    def set(self, account: str, value: str) -> None:
        entries = self._load()
        entries[account] = value
        self._save(entries)

    def delete(self, account: str) -> None:
        entries = self._load()
        entries.pop(account, None)
        self._save(entries)


# ── Backend detection ──────────────────────────────────────────────────────────


def _is_wsl2() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _powershell_accessible() -> bool:
    import subprocess  # noqa: PLC0415
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "exit 0"],
            capture_output=True, timeout=5, check=True,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _dbus_available() -> bool:
    import subprocess  # noqa: PLC0415
    try:
        return subprocess.run(
            ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus",
             "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
            capture_output=True, timeout=2,
        ).returncode == 0
    except Exception:  # noqa: BLE001
        return False


_backend: _Backend | None = None


def _get_backend() -> _Backend:
    global _backend  # noqa: PLW0603
    if _backend is not None:
        return _backend

    # Checked before every selection branch, not once at import: `reset_backend()` can null the
    # cache at any point, and this must hold on the path taken *after* that. See
    # `_FORBID_REAL_BACKEND_ENV`.
    if os.environ.get(_FORBID_REAL_BACKEND_ENV):
        raise RuntimeError(_FORBIDDEN_MSG)

    # An explicit master password is the headless / CI escape hatch: honour it first so the
    # Fernet vault is selected deterministically, even on platforms where a keyring backend
    # imports cleanly but cannot actually reach its secret service (e.g. Linux without a
    # session D-Bus, where SecretService would crash with DBUS_SESSION_BUS_ADDRESS unset).
    if pw := os.environ.get(_MASTER_PW_ENV):
        logger.debug("credential store: Fernet-encrypted vault (master password from env)")
        _backend = _FernetVault(pw)
    elif platform.system() == "Darwin":
        logger.debug("credential store: macOS Keychain")
        _backend = _KeyringBackend("keyring.backends.macOS", "Keyring")
    elif _is_wsl2() and _powershell_accessible():
        logger.debug("credential store: Windows DPAPI (WSL2)")
        _backend = _DPAPIBackend()
    elif platform.system() == "Linux" and os.environ.get("DBUS_SESSION_BUS_ADDRESS") and _dbus_available():
        logger.debug("credential store: SecretService (D-Bus)")
        _backend = _KeyringBackend("keyring.backends.SecretService", "Keyring")
    else:
        raise RuntimeError(_NO_BACKEND_MSG)

    return _backend


# ── Public API ─────────────────────────────────────────────────────────────────


def reset_backend() -> None:
    """Evict the cached backend (tests and after CLI backend-switch)."""
    global _backend  # noqa: PLW0603
    _backend = None


def get(account: str) -> str | None:
    return _get_backend().get(account)


def set_credential(account: str, value: str) -> None:
    _get_backend().set(account, value)


def delete(account: str) -> None:
    _get_backend().delete(account)
