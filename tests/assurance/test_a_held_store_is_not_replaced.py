"""A store file is not replaced, rewritten or restored over while a process has it open.

`init --force` moved a new file onto the store's path while a running backend still held the old
one. That backend went on writing its own write-ahead log at the same path, against a file that was
no longer the one the path named, and the next open reported `database disk image is malformed`.

Whatever opens a store keeps a shared hold on the file beside it for as long as it is open, and the
three operations that swap or rewrite the file — `init_store`, `rotate_key` and an upgrade's restore
— need that hold alone. The kernel owns the hold, so a holder that was killed is not holding.

Every store here is under `tmp_path`, with the in-memory credential backend `conftest.py` installs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: E402
from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: E402
from src.infrastructure.assurance.lifecycle import init_store, rotate_key  # noqa: E402
from tests.support.assurance_store_template import provision_store  # noqa: E402


def _schema_version(store: Any) -> str:
    row = store._require_unlocked().execute(  # noqa: SLF001 — the open handle itself is the subject
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    return str(row["value"])


def _beside(db_path: Path) -> set[str]:
    return {path.name for path in db_path.parent.iterdir()}


class TestReinitialisingIsRefusedWhileTheStoreIsOpen:
    def test_the_open_store_is_left_exactly_as_it_was(self, unlocked_store: Any, tmp_path: Path) -> None:
        db_path = tmp_path / "store.db"
        version = _schema_version(unlocked_store)
        inode, content = os.stat(db_path).st_ino, db_path.read_bytes()
        key = accounts.read(accounts.DB_KEY, db_path)

        with pytest.raises(RuntimeError, match="open in a running process"):
            init_store(db_path, force=True)

        assert os.stat(db_path).st_ino == inode, "the path names a different file than the one held open"
        assert db_path.read_bytes() == content
        assert accounts.read(accounts.DB_KEY, db_path) == key
        assert _schema_version(unlocked_store) == version
        leftovers = {name for name in _beside(db_path) if "initialising" in name or "pre-init" in name}
        assert not leftovers, f"a refused reinitialisation left {leftovers} behind"

    def test_the_refusal_says_how_to_release_the_store(self, unlocked_store: Any, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError) as refusal:
            init_store(tmp_path / "store.db", force=True)

        assert "arch-backend --stop" in str(refusal.value)
        assert "arch-assurance lock" in str(refusal.value)

    def test_it_is_allowed_once_the_store_is_locked(self, tmp_path: Path) -> None:
        db_path = provision_store(tmp_path / "store.db")
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        store.lock()
        before = accounts.read(accounts.DB_KEY, db_path)

        assert init_store(db_path, force=True)["status"] == "initialised"
        assert accounts.read(accounts.DB_KEY, db_path) != before

    def test_a_second_holder_keeps_it_refused_after_the_first_lets_go(self, tmp_path: Path) -> None:
        """A backend and a command line may both have the store open; either one is enough."""
        db_path = provision_store(tmp_path / "store.db")
        first, second = SQLCipherAssuranceStore(db_path), SQLCipherAssuranceStore(db_path)
        first.unlock()
        second.unlock()
        try:
            first.lock()
            with pytest.raises(RuntimeError, match="open in a running process"):
                init_store(db_path, force=True)
        finally:
            second.lock()

    def test_a_first_initialisation_needs_no_store_to_exist(self, tmp_path: Path) -> None:
        db_path = tmp_path / "fresh" / "store.db"

        assert init_store(db_path)["status"] == "initialised"

        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        store.lock()


    def test_the_command_reports_the_refusal_and_changes_no_setting(
        self, unlocked_store: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`init --force` clears the activation gate and writes the storage settings afterwards."""
        import argparse

        from src.infrastructure.cli import _assurance_commands as commands

        def _must_not_be_reached(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("a refused reinitialisation went on to write settings")

        monkeypatch.setattr(commands, "write_storage_config", _must_not_be_reached)
        db_path = tmp_path / "store.db"
        accounts.write(accounts.SETUP_GATE, db_path, "activated")

        status = commands.cmd_init(
            argparse.Namespace(db_path=str(db_path), force=True, backend=None, signals=None, archive_backend=None)
        )

        assert status == 1
        assert "open in a running process" in capsys.readouterr().err
        assert accounts.read(accounts.SETUP_GATE, db_path) == "activated"

    def test_the_file_the_hold_is_taken_on_is_ignored_by_git(self, tmp_path: Path) -> None:
        from src.infrastructure.assurance._store_hold import hold_path

        db_path = tmp_path / "fresh" / "store.db"
        init_store(db_path)

        assert hold_path(db_path).name == "store.db.hold"
        assert "*.db.hold" in (db_path.parent / ".gitignore").read_text().splitlines()


class TestAHoldDoesNotOutliveItsHolder:
    def test_the_file_a_holder_leaves_behind_blocks_nothing(self, tmp_path: Path) -> None:
        """What a killed process leaves is the file; the hold itself went with the process."""
        from src.infrastructure.assurance._store_hold import hold_path

        db_path = provision_store(tmp_path / "store.db")
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        descriptor = store._conns._hold._descriptor  # noqa: SLF001 — dropped as a dying process drops it
        assert descriptor is not None
        os.close(descriptor)
        store._conns._hold._descriptor = None  # noqa: SLF001
        store.lock()
        assert hold_path(db_path).exists(), "the fixture must leave the file for this to test anything"

        assert init_store(db_path, force=True)["status"] == "initialised"

    def test_asking_removes_nothing(self, unlocked_store: Any, tmp_path: Path) -> None:
        """A refusal looked; it did not tidy. What is beside the store is what was there."""
        db_path = tmp_path / "store.db"
        before = _beside(db_path)

        with pytest.raises(RuntimeError):
            init_store(db_path, force=True)

        assert _beside(db_path) == before


class TestWhatCannotBeEstablishedIsRefused:
    def test_an_unreadable_hold_refuses_rather_than_assuming_nobody_is_there(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.assurance import _store_hold

        db_path = provision_store(tmp_path / "store.db")
        content = db_path.read_bytes()

        def _no_locks_here(_descriptor: int, _operation: int) -> None:
            raise OSError(37, "No locks available")

        monkeypatch.setattr(_store_hold.fcntl, "flock", _no_locks_here)

        with pytest.raises(RuntimeError, match="cannot be established"):
            init_store(db_path, force=True)
        assert db_path.read_bytes() == content


class TestAStoreBeingReplacedCannotBeOpened:
    def test_unlocking_is_refused_for_as_long_as_the_replacement_runs(self, tmp_path: Path) -> None:
        from src.infrastructure.assurance._store_hold import sole_access

        db_path = provision_store(tmp_path / "store.db")
        store = SQLCipherAssuranceStore(db_path)

        with sole_access(db_path, to="reinitialise"):
            with pytest.raises(RuntimeError, match="being replaced"):
                store.unlock()
            assert store.is_unlocked() is False

        store.unlock()
        store.lock()


class TestTheOtherWritersOfTheFile:
    def test_a_key_rotation_is_refused_while_the_store_is_open(
        self, unlocked_store: Any, tmp_path: Path
    ) -> None:
        """A rekey rewrites every page under a key the open handle does not have."""
        db_path = tmp_path / "store.db"
        key, content = accounts.read(accounts.DB_KEY, db_path), db_path.read_bytes()
        version = _schema_version(unlocked_store)

        with pytest.raises(RuntimeError, match="open in a running process"):
            rotate_key(db_path)

        assert accounts.read(accounts.DB_KEY, db_path) == key
        assert db_path.read_bytes() == content
        assert not [name for name in _beside(db_path) if name.startswith("store.backup.")]
        assert _schema_version(unlocked_store) == version

    def test_a_key_rotation_goes_ahead_once_the_store_is_locked(self, tmp_path: Path) -> None:
        db_path = provision_store(tmp_path / "store.db")
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        store.lock()

        assert rotate_key(db_path)["status"] == "key_rotated"

    def test_an_upgrade_restore_is_refused_while_the_store_is_open(
        self, unlocked_store: Any, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "store.db"
        handle = _discovered_store_target(db_path)
        copy = handle.backup(tmp_path / "checkpoint")
        assert copy is not None
        content = db_path.read_bytes()

        with pytest.raises(RuntimeError, match="open in a running process"):
            handle.restore(copy)

        assert db_path.read_bytes() == content
        assert _schema_version(unlocked_store)

    def test_an_upgrade_restore_goes_ahead_once_the_store_is_locked(self, tmp_path: Path) -> None:
        db_path = provision_store(tmp_path / "store.db")
        handle = _discovered_store_target(db_path)
        copy = handle.backup(tmp_path / "checkpoint")
        assert copy is not None

        handle.restore(copy)

        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        store.lock()


def _discovered_store_target(db_path: Path) -> Any:
    """The store as an upgrade finds it, so what is tested is the handle a restore really uses."""
    from src.domain.deployment.layout import (
        DeploymentManifest,
        ProvenanceEntry,
        ResolvedPathField,
        SettingsDocumentSelection,
    )
    from src.infrastructure.deployment.discovery import discover_operational_handles

    def located(path: Path) -> ResolvedPathField:
        return ResolvedPathField(path, "compat_default", (ProvenanceEntry("compat_default", str(path)),))

    manifest = DeploymentManifest(
        settings_document=SettingsDocumentSelection(db_path.parent / "settings.yaml", "source_tree_default"),
        workspace_root=None,
        assurance_db_path=located(db_path),
        signals_db_path=located(db_path.parent / "security-signals.db"),
        guidance_cache_root=located(db_path.parent / "guidance-cache"),
        store_backend="sqlcipher",
        signals_backend="sqlcipher-colocated",
        archive_backend="standard",
        assurance_enabled=True,
        archive_identity=None,
    )
    (handle,) = discover_operational_handles(manifest)
    assert handle.target.kind == "assurance_sqlcipher"
    return handle
