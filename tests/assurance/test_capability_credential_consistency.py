"""Regression: the confidential-store capability probe must use the credential abstraction.

It previously called `keyring.get_password` directly, which on a headless runner (no session
D-Bus) raises and is swallowed as "key absent" — so the capability stayed unavailable even
after `arch-assurance init` stored the key via the credential store (e.g. the Fernet vault).
The probe must consult `_credential_store` so it sees whatever backend the store was set up
with. The autouse fixture installs an in-memory backend that is NOT a keyring.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import capability


def test_sqlcipher_available_reads_via_credential_store(tmp_path: Path) -> None:
    db_path = tmp_path / ".arch-assurance" / "store.db"
    # In-memory backend, not the real keyring; scoped to the store the probe will ask about.
    accounts.write(accounts.DB_KEY, db_path, "the-db-key")

    # Key present but no store file yet.
    assert capability._sqlcipher_available(tmp_path) is False

    (tmp_path / ".arch-assurance").mkdir()
    (tmp_path / ".arch-assurance" / "store.db").write_bytes(b"\x00")

    # Key found via the credential store (not raw keyring) + store present -> available.
    assert capability._sqlcipher_available(tmp_path) is True


def test_sqlcipher_unavailable_when_key_absent(tmp_path: Path) -> None:
    (tmp_path / ".arch-assurance").mkdir()
    (tmp_path / ".arch-assurance" / "store.db").write_bytes(b"\x00")

    # Store file present but no key in the credential store.
    assert capability._sqlcipher_available(tmp_path) is False
