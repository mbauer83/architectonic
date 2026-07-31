"""The two ways a store can be lost while every operation reports success.

**Rotation.** `rotate_key` used to run `PRAGMA rekey` and then write the new key unconditionally: no
read to confirm the old key still opened the store, no reopen to confirm the rekey took, no copy of
the file it was rewriting. `PRAGMA key` proves nothing on its own — SQLCipher defers the check to the
first page read — so against a store whose stored key was *already* wrong, the rekey was a silent
no-op and the write replaced the last correct credential with a random one. The store then held
ciphertext nothing on the machine could open, and the command printed `key_rotated`.

That is not hypothetical: it is the fingerprint of the 2026-07-31 incident, where the live store's
`db-encryption-key` was rewritten while its `db-recovery-key` — written only by `init_store`, in the
same breath as the db key — was left untouched. `rotate_key` is the only writer that can produce that
pair of timestamps.

**Write-ahead log.** WAL mode leaves committed pages in `store.db-wal` until something checkpoints.
A clean close of the last connection does it; SIGKILL does not, and this backend has been SIGKILLed
routinely because graceful shutdown hung on an open event stream. Every unflushed page at that moment
is a committed write the next open may discard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import _credential_store as creds

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

from src.infrastructure.assurance import lifecycle  # noqa: E402
from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: E402
from src.infrastructure.assurance.lifecycle import init_store, rotate_key  # noqa: E402

_WRONG_KEY = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"


def _opens(db_path: Path, key: str) -> bool:
    import sqlcipher3  # type: ignore[import-untyped]

    conn = sqlcipher3.connect(str(db_path))
    try:
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


class TestRotationVerifiesBeforeItReplacesTheKey:
    def test_a_healthy_rotation_leaves_the_new_key_working_and_the_old_one_dead(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "store.db"
        init_store(db_path)
        before = accounts.read(accounts.DB_KEY, db_path)
        assert before is not None and _opens(db_path, before)

        result = rotate_key(db_path)

        after = accounts.read(accounts.DB_KEY, db_path)
        assert after is not None and after != before
        assert _opens(db_path, after)
        assert not _opens(db_path, before)
        assert result["status"] == "key_rotated"

    def test_rotation_keeps_a_copy_of_the_file_it_rewrites(self, tmp_path: Path) -> None:
        """A rekey interrupted midway leaves a database neither key opens. The copy is the only
        artefact that survives that, and it is worthless if it is made afterwards."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        original = db_path.read_bytes()

        backup = Path(str(rotate_key(db_path)["pre_rotation_backup"]))

        assert backup.exists()
        assert backup.read_bytes() == original, "the copy must predate the rekey"
        assert db_path.read_bytes() != original, "the store itself must have been rewritten"

    def test_rotation_refuses_when_the_stored_key_does_not_open_the_store(
        self, tmp_path: Path
    ) -> None:
        """The regression. This is the state every key-loss incident starts in, and the old code
        responded by overwriting the credential — turning a store that needed recovery into one
        that could never be recovered, while reporting success."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        # The store's own key, displaced — exactly what an earlier incident leaves behind.
        creds.set_credential(accounts.scoped_account(accounts.DB_KEY, db_path), _WRONG_KEY)

        with pytest.raises(RuntimeError, match="Refusing to rotate"):
            rotate_key(db_path)

        assert accounts.read(accounts.DB_KEY, db_path) == _WRONG_KEY, (
            "a refused rotation must not touch the credential at all"
        )

    def test_a_refused_rotation_leaves_the_store_file_untouched(self, tmp_path: Path) -> None:
        """It refuses *before* the rekey, not after: a rewritten file plus an unchanged credential
        would be a second, different way to lose the store."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        creds.set_credential(accounts.scoped_account(accounts.DB_KEY, db_path), _WRONG_KEY)
        before = db_path.read_bytes()

        with pytest.raises(RuntimeError):
            rotate_key(db_path)

        assert db_path.read_bytes() == before


class TestInitDoesNotDestroyAStoreItCannotReplace:
    """Whatever step of a reinitialisation fails, the previous contents stay reachable with the
    previous key.

    Stated that way rather than as "the file does not change", because the two orderings this has had
    each protected one step and exposed another, and only the *outcome* distinguishes them:

    * removing the database first — a failed credential write left neither a store nor a key;
    * writing the credential first — a failed creation left a populated store whose key had already
      been replaced, which is the unrecoverable shape.

    The store is now built beside the old one and moved in atomically, so every failure leaves the old
    contents either in place or in a backup the old key still opens. That is the property; where the
    bytes happen to sit is not.
    """

    @staticmethod
    def _openable_copies(tmp_path: Path, db_path: Path, key: str) -> list[Path]:
        candidates = [db_path, *sorted(db_path.parent.glob(f"{db_path.name}*.bak"))]
        return [p for p in candidates if p.exists() and _opens(p, key)]

    def test_a_credential_write_failure_leaves_the_previous_store_recoverable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The credential write is the step that fails for reasons outside this process — the key files
        are chmod-protected, and that protection has stopped a write before."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        old_key = accounts.read(accounts.DB_KEY, db_path)
        assert old_key is not None

        def refuse(account: str, value: str) -> None:
            raise RuntimeError("credential store is read-only")

        monkeypatch.setattr(creds, "set_credential", refuse)

        with pytest.raises(RuntimeError, match="read-only"):
            init_store(db_path, force=True)

        assert self._openable_copies(tmp_path, db_path, old_key), (
            "after a failed reinitialisation nothing on disk opens with the key that still exists"
        )

    def test_a_creation_failure_leaves_the_previous_store_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure the other ordering could not survive. Nothing irreversible has happened yet, so
        the store is exactly as it was — not merely recoverable."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        existing = db_path.read_bytes()
        old_key = accounts.read(accounts.DB_KEY, db_path)

        monkeypatch.setattr(
            lifecycle._db_key_guard, "key_opens_store", lambda *_a, **_k: False
        )

        with pytest.raises(RuntimeError, match="cannot be re-opened"):
            init_store(db_path, force=True)

        assert db_path.read_bytes() == existing
        assert accounts.read(accounts.DB_KEY, db_path) == old_key
        assert not list(db_path.parent.glob("*.initialising")), "the abandoned store was left behind"


class TestWriteAheadLogIsFlushedWhileItStillCan:
    @staticmethod
    def _wal(db_path: Path) -> Path:
        return db_path.parent / f"{db_path.name}-wal"

    def test_checkpointing_folds_the_log_back_into_the_store(self, tmp_path: Path) -> None:
        """After a checkpoint there is nothing in the log for a kill to strand."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        try:
            store.create_analysis(name="Rotation Fixture", method="FMEA")
            wal = self._wal(db_path)
            assert wal.exists() and wal.stat().st_size > 0, "expected WAL mode with pending frames"

            assert store._conns.checkpoint() is True
            assert wal.stat().st_size == 0, "TRUNCATE leaves no frames to recover"
        finally:
            store.lock()

    def test_a_locked_store_reports_nothing_to_flush_rather_than_failing(
        self, tmp_path: Path
    ) -> None:
        """It is reached from shutdown paths that must not fail because of it, and a locked store
        is the common case there."""
        db_path = tmp_path / "store.db"
        init_store(db_path)
        store = SQLCipherAssuranceStore(db_path)
        assert store.is_unlocked() is False
        assert store._conns.checkpoint() is False

    def test_locking_the_store_checkpoints_on_the_way_out(self, tmp_path: Path) -> None:
        """Why the backend's teardown locks rather than reaching for a checkpoint: the two
        obligations — flush the log, stop holding an authorised store open — are one call.

        Closing the last connection would normally checkpoint by itself, but only on a clean close
        of *every* connection, and this manager hands one to each thread.
        """
        db_path = tmp_path / "store.db"
        init_store(db_path)
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        store.create_analysis(name="Checkpoint On Lock", method="STPA")
        store.lock()

        wal = self._wal(db_path)
        assert not wal.exists() or wal.stat().st_size == 0
