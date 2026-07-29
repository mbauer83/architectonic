"""Assurance test fixtures — installs a transient in-memory credential backend."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


@pytest.fixture(autouse=True)
def _in_memory_credential_store():
    """Replace the OS credential backend with an isolated in-memory store."""
    _credential_store._backend = _MemoryBackend()
    yield
    _credential_store.reset_backend()


@pytest.fixture()
def unlocked_store(tmp_path: Path) -> Iterator[Any]:
    """A freshly initialised store, unlocked, on a path of its own.

    Path-scoped by construction: the credential accounts a store provisions are keyed by its own
    path, so initialising one here cannot reach the accounts of a real store.
    """
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()
