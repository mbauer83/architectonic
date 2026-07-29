"""No test may reach a real OS credential backend. Ever.

Twice now — 2026-07-20 and 2026-07-28 — a test wrote through the real backend and overwrote the
live assurance store's `db-encryption-key`. The store file is fine both times; the key that
opens it is not, and there is no second key, so the data is gone.

The first guard installed an in-memory backend over the module global. It was defeated because
`reset_backend()` clears that same global: a test that legitimately exercises backend selection
re-armed the hazard for everything that ran after it on that worker. The protection depended on
test ordering, which means it was not protection.

These tests hold the property directly, at the point of failure: with the suite's environment
in force, selecting a real backend raises. That is checked *after* `reset_backend()`, because
that is exactly the state in which the second incident happened.
"""

from __future__ import annotations

import pytest

from src.infrastructure.assurance import _credential_store as cs


def test_the_suite_forbids_real_credential_backends() -> None:
    """The session fixture is in force; without it every other test here proves nothing."""
    import os

    assert os.environ.get(cs._FORBID_REAL_BACKEND_ENV), (
        "the session-scoped guard in tests/conftest.py is not installed"
    )


def test_selecting_a_backend_after_a_reset_raises_instead_of_reaching_the_os() -> None:
    """The exact sequence behind the second incident.

    `reset_backend()` is a legitimate call — the CLI uses it after switching backends, and tests
    of backend selection need it. What must not happen is that the selection which follows it
    reaches a keychain.
    """
    previous = cs._backend
    try:
        cs.reset_backend()

        with pytest.raises(RuntimeError, match="Refusing to select a real OS credential backend"):
            cs._get_backend()
    finally:
        cs._backend = previous


def test_a_write_after_a_reset_cannot_reach_the_os_credential_store() -> None:
    """The operation that did the damage: writing a freshly generated key."""
    previous = cs._backend
    try:
        cs.reset_backend()

        with pytest.raises(RuntimeError, match="Refusing to select a real OS credential backend"):
            cs.set_credential("db-encryption-key.deadbeefcafe", "0" * 64)
    finally:
        cs._backend = previous


def test_an_explicitly_installed_fake_still_works() -> None:
    """The guard must not make credential-dependent tests impossible to write — it only closes
    the fall-through to a real backend."""
    class _Fake:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def get(self, account: str) -> str | None:
            return self.values.get(account)

        def set(self, account: str, value: str) -> None:
            self.values[account] = value

        def delete(self, account: str) -> None:
            self.values.pop(account, None)

    previous = cs._backend
    try:
        cs._backend = _Fake()

        cs.set_credential("db-encryption-key.deadbeefcafe", "abc")

        assert cs.get("db-encryption-key.deadbeefcafe") == "abc"
    finally:
        cs._backend = previous


def test_the_suite_redirects_the_credential_directory_to_a_tmp_dir() -> None:
    """The forbid flag has been bypassed three times by writers outside this process
    (subprocesses, paths around backend selection). The directory redirect is the
    guard that holds regardless: while the suite runs, every file-based credential
    location — inherited by subprocesses via the environment — resolves under a
    throwaway tmp dir, never under the developer's real ~/.config/arch-assurance."""
    import os
    from pathlib import Path

    from src.infrastructure.assurance._credential_store import _CREDENTIALS_DIR_ENV, _config_dir

    configured = os.environ.get(_CREDENTIALS_DIR_ENV)
    assert configured, "session fixture must set the credential-directory override"
    resolved = _config_dir()
    assert resolved == Path(configured)
    real = Path.home() / ".config" / "arch-assurance"
    assert not resolved.is_relative_to(real)


def test_the_directory_override_reaches_the_file_backends() -> None:
    """_DPAPIBackend and _FernetVault must resolve their paths at USE time through
    the override — an import-time constant is exactly how the last accident escaped."""
    import os
    from pathlib import Path

    from src.infrastructure.assurance import _credential_store as cs

    configured = Path(os.environ[cs._CREDENTIALS_DIR_ENV])
    dpapi = cs._DPAPIBackend.__new__(cs._DPAPIBackend)  # no PowerShell probe needed
    assert dpapi._creds == configured / "creds"
    vault = cs._FernetVault("irrelevant")
    assert vault._vault == configured / "vault.enc"
