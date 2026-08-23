"""A store's write-ahead log travels with it, and does not outlive it.

These stores run in WAL mode, so a committed write lands in `<db>-wal` and reaches the main database
file only at a checkpoint. Two operations move a store file around, and each got the log wrong in a
way that only shows up on the day it matters:

* **`backup_store` copied the main file alone.** So the backup was a snapshot from before every
  un-checkpointed commit. Measured: with a table created and a row committed behind an open
  connection, the copy did not lack the row — it did not contain the table. That is the emptiest
  possible backup, produced by the function `init --force` uses to preserve the store it is about to
  destroy, for the person who reinitialised one by mistake.

* **`init_store` left the replaced store's log beside the new file.** SQLite reads `<db>-wal` as
  this database's journal, so a fresh store inherited another database's log. Under SQLCipher the
  keys differ and it fails to open — `database disk image is malformed`, which is how this was
  found. With no cipher to notice, it silently comes up holding the *previous* store's contents:
  a reinitialisation that reports success and changes nothing.

Both are asserted with plain `sqlite3`. The sidecar semantics being tested are SQLite's rather than
SQLCipher's, and a test that needed a real encrypted store would need a keychain, which is what
makes it the kind of test that gets skipped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.assurance.lifecycle import _wal_sidecars, backup_store


def _store_with_an_uncheckpointed_commit(db_path: Path) -> sqlite3.Connection:
    """A WAL-mode database whose only commit is still in the log. The caller closes it."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE finding(claim TEXT)")
    conn.execute("INSERT INTO finding VALUES ('committed, not yet checkpointed')")
    conn.commit()
    return conn


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


class TestABackupIsCompleteEnoughToRestoreFrom:
    def test_it_carries_the_write_ahead_log(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        conn = _store_with_an_uncheckpointed_commit(db)
        try:
            wal, _shm = _wal_sidecars(db)
            assert wal.exists(), "the fixture must leave a log for this to be testing anything"

            backup = Path(str(backup_store(db, backup_path=tmp_path / "b.db")["backup_path"]))
        finally:
            conn.close()

        assert "finding" in _tables(backup), (
            "the backup does not contain the committed table, so the log was left behind"
        )
        assert sqlite3.connect(backup).execute("SELECT claim FROM finding").fetchone() is not None

    def test_the_shared_memory_file_is_not_carried(self, tmp_path: Path) -> None:
        """Scratch state SQLite rebuilds on open. A stale copy is a liability, not a record."""
        db = tmp_path / "store.db"
        conn = _store_with_an_uncheckpointed_commit(db)
        try:
            backup = Path(str(backup_store(db, backup_path=tmp_path / "b.db")["backup_path"]))
        finally:
            conn.close()

        assert not backup.with_name(backup.name + "-shm").exists()

    def test_a_store_with_no_log_still_backs_up(self, tmp_path: Path) -> None:
        """The common case, and the one the copy already handled."""
        db = tmp_path / "store.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE finding(claim TEXT)")
        conn.commit()
        conn.close()

        backup = Path(str(backup_store(db, backup_path=tmp_path / "b.db")["backup_path"]))

        assert "finding" in _tables(backup)
        assert not backup.with_name(backup.name + "-wal").exists()

    def test_a_missing_store_says_so_rather_than_producing_an_empty_backup(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            backup_store(tmp_path / "absent.db")


class TestAReplacedStoreDoesNotLeaveItsLogBehind:
    """`init_store` is not called here: it needs a keychain and generates a real key.

    What is asserted is the property the fix gives it — that after a store file is replaced, no
    sidecar of the replaced database is left at that path — plus, below, the corruption that
    property prevents, so the test says why the property is worth having.
    """

    def test_the_helper_names_both_sidecars_as_sqlite_names_them(self, tmp_path: Path) -> None:
        wal, shm = _wal_sidecars(tmp_path / "store.db")

        assert wal.name == "store.db-wal"
        assert shm.name == "store.db-shm"

    def test_a_fresh_store_inheriting_a_log_comes_up_holding_the_old_one(self, tmp_path: Path) -> None:
        """The failure the sidecar removal exists to prevent, demonstrated rather than described."""
        db = tmp_path / "store.db"
        previous = _store_with_an_uncheckpointed_commit(db)
        try:
            staging = db.with_name(db.name + ".initialising")
            fresh = sqlite3.connect(staging)
            fresh.execute("PRAGMA journal_mode = WAL")
            fresh.execute("CREATE TABLE fresh_schema(x)")
            fresh.commit()
            fresh.close()
            staging.replace(db)  # what init_store does, before it removes the sidecars

            assert _tables(db) == {"finding"}, (
                "expected the stale log to have overwritten the new store — if this fails, "
                "SQLite's behaviour has changed and the sidecar removal needs re-justifying"
            )
        finally:
            previous.close()

    def test_removing_the_sidecars_leaves_the_new_store_intact(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        previous = _store_with_an_uncheckpointed_commit(db)
        try:
            staging = db.with_name(db.name + ".initialising")
            fresh = sqlite3.connect(staging)
            fresh.execute("PRAGMA journal_mode = WAL")
            fresh.execute("CREATE TABLE fresh_schema(x)")
            fresh.commit()
            fresh.close()
            staging.replace(db)
            for sidecar in _wal_sidecars(db):
                sidecar.unlink(missing_ok=True)

            assert _tables(db) == {"fresh_schema"}
        finally:
            previous.close()
