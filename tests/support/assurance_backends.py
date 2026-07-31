"""An unlocked assurance store per backend, so a store-level obligation is proved in all of them.

The port declares the operation; a backend that implements it differently breaks it for whoever is
configured to use that backend, at the moment they use it rather than at startup. So conformance
tests parameterise over these rather than over whichever store the application happened to be tested
against.

The factories lived inside ``test_analysis_deletion_conformance.py``, whose own docstring makes the
argument for moving them: "four copies drift, and the copy that drifts is the one nobody reads." That
is as true of the harness as of the assertions — a second conformance module copying these would be
the fifth and sixth copies of the sqlcipher setup.

PocketBase runs against the shared stub transport. What a conformance test proves is what the
*adapter* does; a running PocketBase would be testing the server. One stub, because two fakes of one
server drift apart as readily as two harnesses do.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.assurance._pocketbase_stub import StubPocketBaseClient


def sqlcipher_store(tmp_path: Path) -> Iterator[Any]:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "conformance.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield store
    store.lock()


def private_git_store(tmp_path: Path) -> Iterator[Any]:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore

    store = PrivateGitAssuranceStore(tmp_path / "assurance-repo")
    store.unlock()
    yield store
    store.lock()


def encrypted_private_git_store(tmp_path: Path) -> Iterator[Any]:
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance import _credential_store as creds
    from src.infrastructure.assurance._encrypted_private_git_store import (
        EncryptedPrivateGitAssuranceStore,
    )

    creds.set_credential("private-git-encryption-key", Fernet.generate_key().decode())
    store = EncryptedPrivateGitAssuranceStore(tmp_path / ".arch-assurance-git")
    store.unlock()
    yield store
    store.lock()


def pocketbase_store(_tmp_path: Path) -> Iterator[Any]:
    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore

    store = PocketBaseAssuranceStore("http://localhost:8090", "admin@example.com", "password")
    store._client = StubPocketBaseClient()  # noqa: SLF001 — stands in for the authenticated client
    yield store


#: Backend name → a factory yielding an unlocked store. All four.
ASSURANCE_BACKENDS: dict[str, Callable[[Path], Iterator[Any]]] = {
    "sqlcipher": sqlcipher_store,
    "private-git": private_git_store,
    "encrypted-private-git": encrypted_private_git_store,
    "pocketbase": pocketbase_store,
}

#: Sorted once, so the parameter list and the test ids cannot fall out of step.
BACKEND_NAMES: list[str] = sorted(ASSURANCE_BACKENDS)
