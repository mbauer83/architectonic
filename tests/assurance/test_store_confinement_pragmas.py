"""The store's confinement guarantees are requested, not inherited from the build.

SQLCipher encrypts the database and the write-ahead log. It does not encrypt a temp b-tree that
SQLite spills for a sort or a join — SQLite writes that outside the encryption boundary.

In the wheel shipped today that never happens: it compiles `SQLITE_TEMP_STORE=2`, so memory is
already the default, and SQLCipher forces secure delete on for an encrypted database. So these
assertions pinned nothing when they were written — which is the point. Neither property was asked
for by this codebase, stated anywhere, or true of any build but this one. Another platform's wheel
compiling `SQLITE_TEMP_STORE=1` would put assurance content on disk in the clear, past every gate,
and nothing would report it.

These tests exist so that a change of dependency fails here rather than silently. They are asserted
against a live connection rather than by reading the DDL, because these are per-connection settings
and this store opens one connection per thread: a pragma applied once, on the opening thread, would
leave every other thread spilling to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

#: `temp_store`: 0 = compile-time default, 1 = FILE, 2 = MEMORY.
TEMP_STORE_MEMORY = 2


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()


def _pragma(store: Any, name: str) -> int:
    """Read one pragma back off a live connection. Rows come back keyed by column name."""
    row = store.unlocked_connection().execute(f"PRAGMA {name}").fetchone()
    return int(dict(row)[name])


class TestTemporaryDataNeverReachesTheDisk:
    def test_temp_store_is_memory(self, store: Any) -> None:
        assert _pragma(store, "temp_store") == TEMP_STORE_MEMORY

    def test_the_store_asks_for_it_rather_than_inheriting_it(self, store: Any) -> None:
        """`0` means "whatever the build defaults to". Today that default is MEMORY, so the
        assertion above would pass on its own — and the next wheel could spill to disk with nothing
        changed here. A non-zero value is the store having asked."""
        assert _pragma(store, "temp_store") != 0


class TestDeletedContentIsOverwritten:
    def test_secure_delete_is_on(self, store: Any) -> None:
        assert _pragma(store, "secure_delete") == 1


class TestTheGuaranteesHoldOnEveryConnection:
    def test_a_second_thread_gets_the_same_settings(self, store: Any) -> None:
        """Connections are per-thread, so a setting applied once on the opening thread would leave
        every other thread spilling to disk. This is the failure the assertions above would miss."""
        import threading

        seen: dict[str, int] = {}

        def _read() -> None:
            seen["temp_store"] = _pragma(store, "temp_store")
            seen["secure_delete"] = _pragma(store, "secure_delete")

        worker = threading.Thread(target=_read)
        worker.start()
        worker.join(timeout=30)

        assert seen == {"temp_store": TEMP_STORE_MEMORY, "secure_delete": 1}

    def test_they_survive_a_lock_and_unlock(self, store: Any) -> None:
        store.lock()
        store.unlock()

        assert _pragma(store, "temp_store") == TEMP_STORE_MEMORY
        assert _pragma(store, "secure_delete") == 1


class TestAStorePredatingThesePragmas:
    def test_an_existing_store_gains_them_on_its_next_open(self, tmp_path: Path) -> None:
        """No migration step exists because none is needed: these are applied on every connection
        open, so a store written before them is confined the moment it is next unlocked."""
        from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
        from src.infrastructure.assurance.lifecycle import init_store

        db_path = tmp_path / "existing" / "store.db"
        init_store(db_path)
        first = SQLCipherAssuranceStore(db_path)
        first.unlock()
        first.create_node("loss", "Something already recorded")
        first.lock()

        reopened = SQLCipherAssuranceStore(db_path)
        reopened.unlock()
        try:
            assert _pragma(reopened, "temp_store") == TEMP_STORE_MEMORY
            assert _pragma(reopened, "secure_delete") == 1
        finally:
            reopened.lock()
