"""An empty confidential store for a test, copied from one initialised once per process.

`init_store` derives its key twice (once to write the schema, once to prove the key reopens what it
wrote) and builds the schema and its migrations, ~0.3 s a store. Most tests that call it want none of
that; they want *an empty store that unlocks*. The suite built 586 of them, most of the cost of every
assurance module it ran.

So `init_store` runs once per process, into a directory of its own, and each test receives a byte copy
of that file under its own path, with the two credentials `init_store` records written for that path.
The copy is what `init_store` would have left: the same schema, the same `schema_meta`, the same two
accounts, path-scoped as the real ones are. What it does not reproduce is the work `init_store` does
*besides* leaving a store — the generated key differing per store, the staging replace, the
`.gitignore` beside it — and a test about any of that calls `init_store` itself.
`tests/architecture/test_tests_reuse_the_store_template.py` holds which tests those are.

The template's credentials are held here, not in the credential backend: every test installs a fresh
in-memory backend, so a key left in one would be gone by the next test.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest


class _TemplateBackend:
    """A private credential backend for the one `init_store` call, so it touches nobody's accounts."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self._values.get(account)

    def set(self, account: str, value: str) -> None:
        self._values[account] = value

    def delete(self, account: str) -> None:
        self._values.pop(account, None)


@dataclass(frozen=True)
class _Template:
    path: Path
    db_key: str
    recovery_key: str


@lru_cache(maxsize=1)
def _template() -> _Template:
    from src.infrastructure.assurance import _credential_accounts as accounts
    from src.infrastructure.assurance import _credential_store
    from src.infrastructure.assurance.lifecycle import init_store

    directory = Path(tempfile.mkdtemp(prefix="assurance-store-template-"))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = directory / "template.db"

    previous = _credential_store._backend  # noqa: SLF001 — swapped for the one call, then restored
    _credential_store._backend = _TemplateBackend()  # noqa: SLF001
    try:
        init_store(path)
        db_key = accounts.read(accounts.DB_KEY, path)
        recovery_key = accounts.read(accounts.RECOVERY_KEY, path)
    finally:
        _credential_store._backend = previous  # noqa: SLF001
    if db_key is None or recovery_key is None:
        raise RuntimeError("init_store recorded no key for the template store")
    return _Template(path, db_key, recovery_key)


def provision_store(db_path: Path) -> Path:
    """Leave at *db_path* an empty, locked store whose keys are recorded — what `init_store` leaves.

    Refuses an existing file, as `init_store` does without ``force``: a test that meant to replace a
    store is testing initialisation and should call it.
    """
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance import _credential_accounts as accounts

    if db_path.exists():
        raise FileExistsError(f"Assurance store already exists at {db_path}")
    template = _template()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template.path, db_path)
    accounts.write(accounts.DB_KEY, db_path, template.db_key)
    accounts.write(accounts.RECOVERY_KEY, db_path, template.recovery_key)
    return db_path


@contextmanager
def unlocked_store_at(db_path: Path) -> Iterator[Any]:
    """An empty store at *db_path*, unlocked for the block and locked after it."""
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

    store = SQLCipherAssuranceStore(provision_store(db_path))
    store.unlock()
    try:
        yield store
    finally:
        store.lock()
