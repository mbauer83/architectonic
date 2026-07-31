"""A credential read never changes a credential — the sixth key-loss incident, as properties.

2026-07-31, evening. The live store's ``db-encryption-key`` was replaced by a key that opened nothing,
and every guard built after the five previous losses was in place and irrelevant, because none of them
is on this path:

1. ``_DPAPIBackend.get`` returned ``None`` for a *failed* read as well as for an absent credential. On
   WSL2 each read spawns ``powershell.exe``; under load — six test workers, a browser suite and a live
   backend — that spawn can exceed its timeout.
2. ``accounts.read`` treated that ``None`` as "this store has no scoped credential yet" and fell back
   to the legacy unscoped account, left over from a store two initialisations earlier.
3. Finding a value there, it **wrote** it to the scoped account, to save a round trip on later reads.

So a read, in the backend process — which no test guard covers — overwrote a working key with a stale
one. Nothing failed, nothing was logged, and the store was unopenable at the next unlock.

Both halves are fixed and both are tested here: a failure to read is now an error rather than an
absence, and a read cannot write at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import _credential_store as creds


class _Recording:
    """A backend that records writes and can be told to fail a read the way a keychain does."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.writes: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    def get(self, account: str) -> str | None:
        if account in self.failing:
            raise creds.CredentialUnavailable(f"simulated keychain failure for {account}")
        return self.values.get(account)

    def set(self, account: str, value: str) -> None:
        self.writes.append((account, value))
        self.values[account] = value

    def delete(self, account: str) -> None:
        self.values.pop(account, None)


@pytest.fixture()
def backend(monkeypatch: pytest.MonkeyPatch) -> _Recording:
    recording = _Recording()
    monkeypatch.setattr(creds, "_backend", recording)
    return recording


_STORE = Path("/workspace/.arch-assurance/store.db")


def test_reading_a_scoped_credential_writes_nothing(backend: _Recording) -> None:
    scoped = accounts.scoped_account(accounts.DB_KEY, _STORE)
    backend.values[scoped] = "the-live-key"

    assert accounts.read(accounts.DB_KEY, _STORE) == "the-live-key"
    assert backend.writes == []


def test_falling_back_to_a_legacy_account_writes_nothing(backend: _Recording) -> None:
    """The regression. The fallback used to copy what it found onto the scoped account; that copy is
    the only step in the whole sequence that destroyed anything."""
    backend.values[accounts.DB_KEY] = "a-key-from-an-older-store"

    assert accounts.read(accounts.DB_KEY, _STORE) == "a-key-from-an-older-store"
    assert backend.writes == [], (
        "reading migrated a legacy credential onto the scoped account — the write that cost the store"
    )


def test_a_failed_read_is_an_error_not_an_absence(backend: _Recording) -> None:
    """Step 1 of the incident. With the failure flattened into ``None``, the caller below cannot tell
    a slow keychain from an unconfigured store, and every decision it makes from there is wrong."""
    scoped = accounts.scoped_account(accounts.DB_KEY, _STORE)
    backend.values[scoped] = "the-live-key"
    backend.failing.add(scoped)

    with pytest.raises(creds.CredentialUnavailable):
        accounts.read(accounts.DB_KEY, _STORE)


def test_a_failed_scoped_read_never_reaches_the_legacy_account(backend: _Recording) -> None:
    """The composition of the two fixes, which is what makes the incident impossible rather than
    unlikely: the error stops the sequence before the fallback is consulted at all."""
    scoped = accounts.scoped_account(accounts.DB_KEY, _STORE)
    backend.values[scoped] = "the-live-key"
    backend.values[accounts.DB_KEY] = "a-key-from-an-older-store"
    backend.failing.add(scoped)

    with pytest.raises(creds.CredentialUnavailable):
        accounts.read(accounts.DB_KEY, _STORE)
    assert backend.writes == []


def test_an_absent_credential_is_still_absent(backend: _Recording) -> None:
    """The distinction has to cut both ways: a store that genuinely has no key must still report
    none, or `arch-assurance status` would call an uninitialised store broken."""
    assert accounts.read(accounts.DB_KEY, _STORE) is None
    assert accounts.present(accounts.DB_KEY, _STORE) is False


def test_two_stores_do_not_share_an_account() -> None:
    """Unchanged, and re-stated because it is the property the scoping exists for: the fallback is the
    only thing that ever crossed between stores, and it can no longer write."""
    other = Path("/workspace/other/.arch-assurance/store.db")
    assert accounts.scoped_account(accounts.DB_KEY, _STORE) != accounts.scoped_account(
        accounts.DB_KEY, other
    )
