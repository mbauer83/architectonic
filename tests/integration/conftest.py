"""Integration-test fixtures.

Installs the same transient in-memory credential backend used by the assurance
unit tests, so the SQLCipher store can be initialised and unlocked without an OS
keychain. Kept local to this package so integration tests are self-contained.

It is installed at two scopes deliberately. The session guard in the root conftest refuses to
select a real OS backend at all, so anything that provisions a store key must supply a fake one —
and a *function*-scoped fixture is set up too late for a module-scoped fixture that initialises a
store while building its own expensive shared state. Both scopes share one installer rather than
one class with two copies of the install step.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from src.infrastructure.assurance import _credential_store


class _MemoryBackend:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self._store.get(account)

    def set(self, account: str, value: str) -> None:
        self._store[account] = value

    def delete(self, account: str) -> None:
        self._store.pop(account, None)


@contextmanager
def _installed_memory_backend() -> Iterator[None]:
    """Replace the OS credential backend with an isolated in-memory store."""
    _credential_store._backend = _MemoryBackend()
    try:
        yield
    finally:
        _credential_store.reset_backend()


@pytest.fixture(autouse=True)
def _in_memory_credential_store() -> Iterator[None]:
    with _installed_memory_backend():
        yield


@pytest.fixture(autouse=True, scope="module")
def _in_memory_credential_store_for_module_scoped_fixtures() -> Iterator[None]:
    """Covers module-scoped fixtures, which are built before any function-scoped fixture runs."""
    with _installed_memory_backend():
        yield
