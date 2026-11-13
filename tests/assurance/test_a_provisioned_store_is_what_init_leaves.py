"""A store copied from the per-process template is the store `init_store` would have left.

The template exists so a test pays for one initialisation per process, not one per test. It is only
sound while the copy is indistinguishable from a fresh `init_store` for everything a test can observe
through the store: the schema, the recorded schema version, the two path-scoped credentials, and an
empty graph — and while two copies share nothing but a key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.support.assurance_store_template import provision_store, unlocked_store_at

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


def _shape(store: Any) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    conn = store.unlocked_connection()
    schema = conn.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
    meta = conn.execute("SELECT key, value FROM schema_meta ORDER BY key").fetchall()
    return [tuple(row) for row in schema], [tuple(row) for row in meta]


def test_the_copy_has_the_schema_and_version_init_writes(tmp_path: Path) -> None:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    init_store(tmp_path / "initialised" / "store.db")
    initialised = SQLCipherAssuranceStore(tmp_path / "initialised" / "store.db")
    initialised.unlock()
    try:
        with unlocked_store_at(tmp_path / "provisioned" / "store.db") as provisioned:
            assert _shape(provisioned) == _shape(initialised)
            assert provisioned.list_nodes() == []
    finally:
        initialised.lock()


def test_the_copy_records_both_credentials_for_its_own_path(tmp_path: Path) -> None:
    from src.infrastructure.assurance import _credential_accounts as accounts

    db_path = provision_store(tmp_path / "store.db")

    assert accounts.present(accounts.DB_KEY, db_path)
    assert accounts.present(accounts.RECOVERY_KEY, db_path)


def test_two_copies_are_independent_stores(tmp_path: Path) -> None:
    with unlocked_store_at(tmp_path / "a.db") as first, unlocked_store_at(tmp_path / "b.db") as second:
        first.create_node("loss", "Only in the first")

        assert [node["name"] for node in first.list_nodes()] == ["Only in the first"]
        assert second.list_nodes() == []


def test_an_existing_store_is_never_overwritten(tmp_path: Path) -> None:
    db_path = provision_store(tmp_path / "store.db")

    with pytest.raises(FileExistsError):
        provision_store(db_path)
