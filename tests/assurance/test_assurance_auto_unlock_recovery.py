"""Auto-unlock: it recovers from a transient credential outage, and it says why it didn't unlock.

Incident behind these tests: the assurance store showed as locked while the OS keychain was
perfectly healthy. Auto-unlock ran exactly once, when the workspace's bundle was built, and the
bundle is cached for the life of the process — so a credential backend that was momentarily
unreachable at startup (on WSL2, a `powershell.exe` interop probe exceeding its timeout under
load) left the store locked until a restart. Both silent branches logged at debug, so there was
nothing to find in the log either.

The activation gate itself is unchanged: a store that was never activated stays locked no matter
how often the retry runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.domain.clock import frozen_now
from src.infrastructure.assurance import store_factory

#: The store the bundles below stand for. The activation gate is scoped to a store, so a bundle
#: carries the path its gate belongs to.
STORE_PATH = Path("/ws/.arch-assurance/store.db")


class _Store:
    def __init__(self) -> None:
        self.unlocked = False
        self.unlock_calls = 0

    def is_unlocked(self) -> bool:
        return self.unlocked

    def unlock(self) -> None:
        self.unlock_calls += 1
        self.unlocked = True


class _RefusingStore(_Store):
    def unlock(self) -> None:
        self.unlock_calls += 1
        raise RuntimeError("key absent")


@pytest.fixture(autouse=True)
def _unattended_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the deployment shape, because the gate is only consulted once the policy allows it.

    These tests are about the activation gate and how a failed read is reported. Whether a newly
    started process may consult the gate at all is a prior, separate question the deployment's
    activation policy answers. 'persistent' is the deployment where a startup unlock happens —
    an unattended server, where a reboot must not take the capability down — so pinning it here
    leaves the gate as the only thing under test.
    """
    monkeypatch.setattr(
        store_factory.storage_settings, "storage_assurance_activation_policy", lambda: "persistent",
    )


@pytest.fixture()
def bundle(monkeypatch: pytest.MonkeyPatch) -> store_factory._AssuranceBundle:
    """A cached, still-locked key-backed bundle — the state a failed startup unlock leaves.

    `private-git` rather than `sqlcipher` so the fixture needs no live encrypted connection: both
    unlock from an OS-keychain key, which is what the retry is about.
    """
    store = _Store()
    built = store_factory._AssuranceBundle(
        store=store,  # type: ignore[arg-type]
        archive=object(),  # type: ignore[arg-type]
        store_backend="private-git",
        signals_backend="public-sqlite",
        archive_backend="standard",
        store_scope=STORE_PATH,
    )
    monkeypatch.setattr(store_factory, "_instances", {"/ws": built})
    monkeypatch.setattr(store_factory, "_last_auto_unlock_attempt", {"/ws": 0})
    return built


def _gate(monkeypatch: pytest.MonkeyPatch, *, confirmed: object) -> None:
    """Stub the activation-gate read. `confirmed` may be a value or an exception to raise."""
    from src.infrastructure.assurance import _credential_store as creds

    def _get(account: str) -> object:
        if isinstance(confirmed, Exception):
            raise confirmed
        return confirmed

    monkeypatch.setattr(creds, "get", _get)


class TestRetry:
    def test_a_locked_bundle_unlocks_once_credentials_come_back(
        self, bundle: store_factory._AssuranceBundle, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _gate(monkeypatch, confirmed="yes")

        with frozen_now("2026-07-25T02:00:00Z"):
            store_factory._retry_auto_unlock_if_due("/ws", bundle)

        assert bundle.store.is_unlocked()

    def test_an_unactivated_store_stays_locked_however_often_it_is_retried(
        self, bundle: store_factory._AssuranceBundle, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The activation gate still decides — the retry does not widen anything."""
        _gate(monkeypatch, confirmed=None)

        for minute in range(3):
            with frozen_now(f"2026-07-25T02:0{minute}:00Z"):
                store_factory._retry_auto_unlock_if_due("/ws", bundle)

        assert not bundle.store.is_unlocked()
        assert bundle.store.unlock_calls == 0  # type: ignore[attr-defined]

    def test_retries_are_throttled_so_a_locked_store_costs_one_probe_per_window(
        self, bundle: store_factory._AssuranceBundle, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reading the gate is a credential-backend round trip; a locked store must not pay for
        one on every single request.

        Counted per *probe*, by the scoped account each one asks for first. A probe that finds
        nothing there also consults the unscoped account a pre-scoping store would have used, which
        is a second round trip but only for a store that has never been activated — exactly the
        state this throttle already limits to one probe per window.
        """
        from src.infrastructure.assurance import _credential_accounts as accounts
        from src.infrastructure.assurance import _credential_store as creds

        reads: list[str] = []
        monkeypatch.setattr(creds, "get", lambda account: reads.append(account))
        scoped = accounts.scoped_account(accounts.SETUP_GATE, STORE_PATH)

        def probes() -> int:
            return sum(1 for account in reads if account == scoped)

        with frozen_now("2026-07-25T02:00:00Z"):
            for _ in range(5):
                store_factory._retry_auto_unlock_if_due("/ws", bundle)
        assert probes() == 1, "repeated access inside one window must read the gate once"

        with frozen_now("2026-07-25T02:00:29Z"):
            store_factory._retry_auto_unlock_if_due("/ws", bundle)
        assert probes() == 1, "still inside the window"

        with frozen_now("2026-07-25T02:00:31Z"):
            store_factory._retry_auto_unlock_if_due("/ws", bundle)
        assert probes() == 2, "past the window, it tries again"

    def test_an_already_unlocked_store_is_never_probed(
        self, bundle: store_factory._AssuranceBundle, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bundle.store.unlocked = True  # type: ignore[attr-defined]
        _gate(monkeypatch, confirmed=RuntimeError("must not be called"))

        with frozen_now("2026-07-25T03:00:00Z"):
            store_factory._retry_auto_unlock_if_due("/ws", bundle)

        assert bundle.store.is_unlocked()

    def test_a_session_authenticated_backend_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PocketBase authenticates per session, not from an OS-keychain key, so it has no
        activation gate to retry."""
        store = _Store()
        pocketbase = store_factory._AssuranceBundle(
            store=store,  # type: ignore[arg-type]
            archive=object(),  # type: ignore[arg-type]
            store_backend="pocketbase",
            signals_backend="public-sqlite",
            archive_backend="standard",
            store_scope=STORE_PATH,
        )
        _gate(monkeypatch, confirmed=RuntimeError("must not be called"))
        monkeypatch.setattr(store_factory, "_last_auto_unlock_attempt", {})

        with frozen_now("2026-07-25T04:00:00Z"):
            store_factory._retry_auto_unlock_if_due("/pb", pocketbase)

        assert not store.is_unlocked()


class TestReportsWhyItDidNotUnlock:
    def test_an_unreachable_credential_backend_is_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The failure that made this inexplicable: the environment lost the credential backend,
        the capability silently switched off, and nothing above debug said so."""
        store = _Store()
        _gate(monkeypatch, confirmed=RuntimeError("no secure credential backend"))

        with caplog.at_level(logging.INFO):
            store_factory.try_auto_unlock(store, "sqlcipher", STORE_PATH)  # type: ignore[arg-type]

        assert not store.is_unlocked()
        (record,) = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert "no secure credential backend is reachable" in record.getMessage()

    def test_a_store_that_was_never_activated_is_only_a_hint(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A fresh install is a normal state, so it must not cry wolf on every start."""
        store = _Store()
        _gate(monkeypatch, confirmed=None)

        with caplog.at_level(logging.INFO):
            store_factory.try_auto_unlock(store, "sqlcipher", STORE_PATH)  # type: ignore[arg-type]

        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
        assert any("arch-assurance unlock" in r.getMessage() for r in caplog.records)

    def test_an_uninitialised_store_is_distinguished_from_a_broken_one(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        store = _RefusingStore()
        _gate(monkeypatch, confirmed="yes")

        with caplog.at_level(logging.INFO):
            store_factory.try_auto_unlock(store, "sqlcipher", STORE_PATH)  # type: ignore[arg-type]

        assert not store.is_unlocked()
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
        assert any("key absent or store not initialised" in r.getMessage() for r in caplog.records)

    def test_a_successful_unlock_says_so(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        store = _Store()
        _gate(monkeypatch, confirmed="yes")

        with caplog.at_level(logging.INFO):
            store_factory.try_auto_unlock(store, "sqlcipher", STORE_PATH)  # type: ignore[arg-type]

        assert store.is_unlocked()
        assert any("auto-unlocked from OS keychain" in r.getMessage() for r in caplog.records)


def test_clearing_the_cache_forgets_the_retry_window(tmp_path: Path) -> None:
    """A rebuilt bundle runs its own startup unlock, so a stale window must not suppress it."""
    store_factory._last_auto_unlock_attempt["/stale"] = 12345
    store_factory.clear_factory_cache()
    assert store_factory._last_auto_unlock_attempt == {}
