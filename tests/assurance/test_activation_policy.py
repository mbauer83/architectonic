"""Opening the assurance store on process start is a deployment policy, not an implication.

Before this, one fact did the work of a policy nobody had stated: "I once ran `unlock` on this
machine" silently meant "every future process start, unattended, on any deployment shape". The
keychain gate records that the store was ceremonially activated once — a fact about the store —
which is not the same question as whether *this* process may open it unattended.

A wall-clock activation window was rejected as the alternative: it has no coherent behaviour when
it expires inside a long-running server process, and elapsed time expresses nobody's intent.

The bound these tests do *not* claim: the key stays in the OS keychain under either policy, so
this governs application-level access, not key extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import store_factory

#: The store these tests stand in for. The gate is scoped to it, so the fixtures below write and
#: read it through the same accounts API production does rather than matching an account name.
STORE_PATH = Path("/ws/.arch-assurance/store.db")


class _FakeStore:
    def __init__(self) -> None:
        self.unlocked = False
        self.unlock_calls = 0

    def is_unlocked(self) -> bool:
        return self.unlocked

    def unlock(self) -> None:
        self.unlock_calls += 1
        self.unlocked = True

    def lock(self) -> None:
        self.unlocked = False


@pytest.fixture(autouse=True)
def _reset_process_authorization() -> Iterator[None]:
    """Authorization is process state, so it must not leak between tests."""
    store_factory.revoke_process_authorization()
    yield
    store_factory.revoke_process_authorization()


@pytest.fixture()
def activated_gate() -> None:
    """This store activated once, as `unlock` records it. The suite-wide in-memory credential
    backend holds it, so nothing reaches the real OS credential store."""
    accounts.write(accounts.SETUP_GATE, STORE_PATH, "1")


def _set_policy(monkeypatch: pytest.MonkeyPatch, policy: str) -> None:
    monkeypatch.setattr(
        store_factory.storage_settings, "storage_assurance_activation_policy", lambda: policy,
    )


def _attempt(store: Any) -> None:
    store_factory.try_auto_unlock(store, "sqlcipher", STORE_PATH)


class TestManualIsTheDefault:
    def test_the_shipped_default_is_manual(self) -> None:
        """Fail-closed, chosen while no deployment uses the capability, so adoption costs nothing."""
        from src.config.storage_settings import storage_assurance_activation_policy

        assert storage_assurance_activation_policy() == "manual"

    def test_a_new_process_starts_locked_even_though_the_gate_is_set(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        _set_policy(monkeypatch, "manual")
        store = _FakeStore()

        _attempt(store)

        assert not store.unlocked
        assert store.unlock_calls == 0

    def test_authorizing_the_process_opens_the_store(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        """This is what `unlock` grants the running process; without it the command does nothing."""
        _set_policy(monkeypatch, "manual")
        store = _FakeStore()

        store_factory.authorize_process()
        _attempt(store)

        assert store.unlocked

    def test_authorization_still_requires_the_activation_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Authorizing a process must not bypass the ceremony the gate records."""
        _set_policy(monkeypatch, "manual")
        store = _FakeStore()

        store_factory.authorize_process()
        _attempt(store)

        assert not store.unlocked


class TestPersistentSuitsAnUnattendedDeployment:
    def test_a_new_process_opens_the_store_from_the_gate(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        _set_policy(monkeypatch, "persistent")
        store = _FakeStore()

        _attempt(store)

        assert store.unlocked

    def test_an_unactivated_store_still_stays_locked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_policy(monkeypatch, "persistent")
        store = _FakeStore()

        _attempt(store)

        assert not store.unlocked


class TestRevocationTakesEffectImmediately:
    def test_revoking_closes_a_store_that_is_already_open(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        """Revoking at the next start only would let `lock` report success while access stayed open."""
        _set_policy(monkeypatch, "manual")
        store = _FakeStore()
        store_factory.authorize_process()
        _attempt(store)
        assert store.unlocked

        bundle = type("_Bundle", (), {"store": store})()
        monkeypatch.setitem(store_factory._instances, "revocation-probe", bundle)  # noqa: SLF001
        store_factory.revoke_process_authorization()

        assert not store.unlocked
        assert not store_factory.is_process_authorized()

    def test_a_revoked_process_does_not_reopen_the_store(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        _set_policy(monkeypatch, "manual")
        store = _FakeStore()
        store_factory.authorize_process()
        store_factory.revoke_process_authorization()

        _attempt(store)

        assert not store.unlocked


class TestFailClosed:
    def test_an_unrecognised_policy_leaves_the_store_locked(
        self, monkeypatch: pytest.MonkeyPatch, activated_gate: None
    ) -> None:
        """A misspelt policy must not grant the more permissive behaviour."""
        def _raise() -> str:
            raise ValueError("Unknown storage.assurance.activation_policy: 'persistant'.")

        monkeypatch.setattr(
            store_factory.storage_settings, "storage_assurance_activation_policy", _raise,
        )
        store = _FakeStore()

        _attempt(store)

        assert not store.unlocked

    def test_the_settings_accessor_rejects_an_unrecognised_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.config import settings, storage_settings

        monkeypatch.setattr(settings, "load_settings", lambda: {
            "storage": {"assurance": {"activation_policy": "persistant"}},
        })

        with pytest.raises(ValueError, match="activation_policy"):
            storage_settings.storage_assurance_activation_policy()

    def test_an_unreachable_credential_backend_leaves_the_store_locked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent loss of the whole capability, so it must fail closed rather than open."""
        from src.infrastructure.assurance import _credential_store as creds

        def _unreachable(_account: str) -> str | None:
            raise RuntimeError("no secure credential backend is reachable")

        monkeypatch.setattr(creds, "get", _unreachable)
        _set_policy(monkeypatch, "persistent")
        store = _FakeStore()

        _attempt(store)

        assert not store.unlocked
