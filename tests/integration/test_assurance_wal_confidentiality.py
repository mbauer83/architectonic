"""WAL confidentiality: no plaintext assurance content reaches disk.

Switching the store to WAL mode adds ``-wal``/``-shm`` sidecar files. SQLCipher
encrypts the WAL, but the project's no-plaintext-on-disk constraint requires this
to be *proven*, not assumed. These tests write a unique marker into the store and
assert it never appears in any on-disk artifact, and that the sidecars are covered
by the store directory's ``.gitignore``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_MARKER = "PLAINTEXT-CANARY-7f3a9c21-assurance-secret"


def test_no_plaintext_marker_in_any_on_disk_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / ".arch-assurance" / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    try:
        # Write the marker into node name + content and the audit log.
        store.create_node("hazard", _MARKER, concern_class="safety", content=_MARKER)
        archive = SQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001
        archive.append("TEST", payload={"secret": _MARKER})
    finally:
        store.lock()

    marker_bytes = _MARKER.encode()
    inspected = []
    for path in db_path.parent.iterdir():
        if path.is_file():
            inspected.append(path.name)
            data = path.read_bytes()
            assert marker_bytes not in data, f"plaintext marker leaked into {path.name}"
    # The DB file at minimum must have been inspected.
    assert any(name.startswith("store.db") for name in inspected)


def test_sidecars_are_gitignored(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / ".arch-assurance" / "store.db"
    init_store(db_path)
    gitignore = (db_path.parent / ".gitignore").read_text()
    assert "*.db" in gitignore
    assert "*.db-wal" in gitignore
    assert "*.db-shm" in gitignore
