"""Regression: credential backend selection for headless / CI environments.

On a CI runner the SecretService keyring backend imports cleanly but crashes at runtime when
``DBUS_SESSION_BUS_ADDRESS`` is unset. An explicit ``ARCH_ASSURANCE_MASTER_PASSWORD`` is the
headless escape hatch and must select the Fernet vault first, regardless of platform; and a
Linux host without a session bus must never be routed to SecretService.

These are the only tests in the suite that exercise real backend *selection*, so they are also
the only ones that opt out of the suite-wide refusal to select one (see
``_FORBID_REAL_BACKEND_ENV``). The opt-out is per-test, undone by ``monkeypatch`` at teardown,
and safe only because selection is all these assert: nothing here reads or writes a credential,
so no real keychain or vault is touched. Any test that needs a *working* credential store must
install an explicit fake instead of copying this pattern.
"""

from __future__ import annotations

import pytest

from src.infrastructure.assurance import _credential_store as cs


@pytest.fixture
def selection_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the suite-wide selection ban for one test, and only for selection."""
    monkeypatch.delenv(cs._FORBID_REAL_BACKEND_ENV, raising=False)


def test_master_password_env_selects_fernet_vault(
    monkeypatch: pytest.MonkeyPatch, selection_allowed: None,
) -> None:
    monkeypatch.setattr(cs, "_backend", None)
    monkeypatch.setenv(cs._MASTER_PW_ENV, "ci-secret")
    monkeypatch.setattr(cs.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)

    backend = cs._get_backend()

    assert isinstance(backend, cs._FernetVault)


def test_linux_without_session_bus_is_not_routed_to_secretservice(
    monkeypatch: pytest.MonkeyPatch, selection_allowed: None,
) -> None:
    monkeypatch.setattr(cs, "_backend", None)
    monkeypatch.delenv(cs._MASTER_PW_ENV, raising=False)
    monkeypatch.setattr(cs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(cs, "_is_wsl2", lambda: False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)

    # No usable backend rather than a runtime D-Bus crash. Asserted on the message, because
    # with the selection ban in force this raises RuntimeError too — and a test that passes
    # for the wrong reason is how the ban would hide a real regression here.
    with pytest.raises(RuntimeError, match="No secure credential backend is available"):
        cs._get_backend()
