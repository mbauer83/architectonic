"""A store's secrets belong to that store, and initialising one cannot reach another's.

This is the regression test for a real, unrecoverable data loss. The credential accounts were bare
constants shared by every store on the machine, so `init_store` on *any* path overwrote whichever
store held `db-encryption-key` — and it writes `db-recovery-key` in the same call, so the recovery
key was destroyed alongside the thing it exists to recover. A temporary store under a temp directory
was enough to do it, permanently, with no error raised anywhere.

The pytest-level credential guard did not and could not prevent it: the call that did the damage ran
outside pytest. Isolation in the test harness is not a substitute for the production code being
unable to do the wrong thing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def live_store(tmp_path: Path) -> Any:
    """A store standing in for the one an operator depends on."""
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "live" / "store.db"
    init_store(db_path)
    return db_path


class TestInitialisingOneStoreLeavesAnotherAlone:
    def test_the_live_store_still_opens(self, live_store: Path, tmp_path: Path) -> None:
        """The whole incident in one assertion."""
        from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
        from src.infrastructure.assurance.lifecycle import init_store

        init_store(tmp_path / "throwaway" / "store.db")

        opened = SQLCipherAssuranceStore(live_store)
        opened.unlock()
        assert opened.is_unlocked()
        opened.lock()

    def test_its_key_is_unchanged(self, live_store: Path, tmp_path: Path) -> None:
        from src.infrastructure.assurance.lifecycle import init_store

        before = accounts.read(accounts.DB_KEY, live_store)
        init_store(tmp_path / "throwaway" / "store.db")

        assert accounts.read(accounts.DB_KEY, live_store) == before

    def test_its_recovery_key_is_unchanged(self, live_store: Path, tmp_path: Path) -> None:
        """The recovery key was overwritten in the same call as the key it insures — so losing one
        meant losing both, and the recovery path protected against nothing."""
        from src.infrastructure.assurance.lifecycle import init_store

        before = accounts.read(accounts.RECOVERY_KEY, live_store)
        init_store(tmp_path / "throwaway" / "store.db")

        assert accounts.read(accounts.RECOVERY_KEY, live_store) == before

    def test_the_two_stores_hold_different_keys(self, live_store: Path, tmp_path: Path) -> None:
        from src.infrastructure.assurance.lifecycle import init_store

        other = tmp_path / "throwaway" / "store.db"
        init_store(other)

        assert accounts.read(accounts.DB_KEY, live_store) != accounts.read(accounts.DB_KEY, other)


class TestScoping:
    def test_two_paths_get_two_accounts(self, tmp_path: Path) -> None:
        left = accounts.scoped_account(accounts.DB_KEY, tmp_path / "a" / "store.db")
        right = accounts.scoped_account(accounts.DB_KEY, tmp_path / "b" / "store.db")

        assert left != right

    def test_one_path_is_stable_across_calls(self, tmp_path: Path) -> None:
        """An account name that varied per call would lose the key on the next read."""
        path = tmp_path / "a" / "store.db"

        assert accounts.scoped_account(accounts.DB_KEY, path) == accounts.scoped_account(
            accounts.DB_KEY, path,
        )

    def test_the_filesystem_layout_is_not_published_in_the_account_name(self, tmp_path: Path) -> None:
        """Account names are visible in OS credential UIs; the path is hashed, not embedded."""
        path = tmp_path / "some-revealing-directory" / "store.db"

        assert "some-revealing-directory" not in accounts.scoped_account(accounts.DB_KEY, path)


class TestAStorePredatingTheScoping:
    """Reading falls back to the unscoped account, so an existing store keeps opening with no
    migration step and no operator action."""

    def test_an_unscoped_secret_is_still_found(self, tmp_path: Path) -> None:
        from src.infrastructure.assurance import _credential_store as creds

        creds.set_credential(accounts.DB_KEY, "the-old-global-key")

        assert accounts.read(accounts.DB_KEY, tmp_path / "store.db") == "the-old-global-key"

    def test_a_scoped_secret_wins_over_an_unscoped_one(self, tmp_path: Path) -> None:
        from src.infrastructure.assurance import _credential_store as creds

        path = tmp_path / "store.db"
        creds.set_credential(accounts.DB_KEY, "the-old-global-key")
        accounts.write(accounts.DB_KEY, path, "this-store's-key")

        assert accounts.read(accounts.DB_KEY, path) == "this-store's-key"

    def test_writing_never_touches_the_unscoped_account(self, tmp_path: Path) -> None:
        """A write that cleaned up the unscoped account would be the original bug wearing a hat: a
        store at some other path deleting the secret of a store that predates scoping."""
        from src.infrastructure.assurance import _credential_store as creds

        creds.set_credential(accounts.DB_KEY, "the-old-global-key")
        accounts.write(accounts.DB_KEY, tmp_path / "elsewhere" / "store.db", "unrelated")

        assert creds.get(accounts.DB_KEY) == "the-old-global-key"


class TestRevocationActuallyRevokes:
    def test_clearing_removes_the_unscoped_account_too(self, tmp_path: Path) -> None:
        """Otherwise the next read falls back to it and re-opens a store just locked."""
        from src.infrastructure.assurance import _credential_store as creds

        path = tmp_path / "store.db"
        creds.set_credential(accounts.SETUP_GATE, "1")
        accounts.write(accounts.SETUP_GATE, path, "1")

        accounts.clear(accounts.SETUP_GATE, path)

        assert accounts.read(accounts.SETUP_GATE, path) is None
