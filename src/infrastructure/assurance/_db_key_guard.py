"""The one door through which a store's encryption key may be replaced.

Five times a live assurance store has become permanently unopenable — 2026-07-20, -07-28, -07-29
twice, -07-31 — always the same way: the ciphertext survived and the key did not. Each time the
repair hardened the *entrance the last incident came through*, and every one of those entrances was
on the test side: an in-memory backend defeated by ``reset_backend()``; an in-process forbid flag
that a subprocess never saw; a credentials-directory redirect that a subprocess launched with a
replaced environment never inherited.

The fifth incident came through production code. On disk it left an unmistakable pair of timestamps:
the store's ``db-encryption-key`` rewritten, its ``db-recovery-key`` — which ``init_store`` writes in
the same breath as the db key — untouched for two days. Only one code path can produce that pair, and
it was ``rotate_key``, which wrote a freshly generated key without ever confirming that the rekey it
had just attempted actually took. No test-side guard could have stopped it, and four rounds of them
were built without anyone asking the one-line question: *what else writes this credential?*

So this module answers that question structurally rather than case by case. Replacing a db key is not
an ordinary credential write, because the key and the file it opens are one fact split across two
places, and a write that breaks their correspondence is unrecoverable. Every writer therefore has to
say which of exactly two things it is doing:

* **rekeying** an existing store — the new key must be *proven* to open the file, here, before the
  credential is replaced;
* **replacing** the store outright — the file is about to be, or has just been, created from scratch,
  and the caller accepts that whatever the old key opened is gone.

There is no third case, and ``tests/architecture/test_db_key_writes_go_through_the_guard.py`` holds
that no code outside this module writes the account directly. That is the part four earlier fixes
lacked: a guard on the *class* of writes, not on the entrance the last one used.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.infrastructure.assurance import _credential_accounts as accounts

logger = logging.getLogger(__name__)


def key_opens_store(db_path: Path, key: str) -> bool:
    """Whether ``key`` actually decrypts the store at ``db_path``.

    Reads a page. ``PRAGMA key`` on its own proves nothing — SQLCipher defers the check to the first
    read — which is exactly why a rekey could appear to succeed and a key could be stored that opened
    nothing.
    """
    import sqlcipher3  # type: ignore[import-untyped]

    connection = sqlcipher3.connect(str(db_path))
    try:
        connection.execute(f"PRAGMA key = '{key}'")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception:  # noqa: BLE001 - any failure to read means the key does not open it
        return False
    else:
        return True
    finally:
        connection.close()


def store_db_key_for_rekey(db_path: Path, key: str) -> None:
    """Replace the stored key for an existing store, proving first that it opens it.

    Refuses otherwise, leaving the previous credential in place. That refusal is the whole point: at
    the moment of the fifth incident the store still had a key somewhere, and overwriting it turned a
    recoverable situation into an unrecoverable one.
    """
    if not db_path.exists():
        raise RuntimeError(
            f"Refusing to store a rekeyed credential for {db_path}: there is no store at that path. "
            "Use store_db_key_for_new_store if the store is being created."
        )
    if not key_opens_store(db_path, key):
        raise RuntimeError(
            f"Refusing to store a key that does not open {db_path}. The existing credential is "
            "untouched. This is the check whose absence has made this store unopenable five times: "
            "a rekey that silently did nothing, followed by a blind write of the new key."
        )
    accounts.write(accounts.DB_KEY, db_path, key)
    logger.info("Assurance store key replaced for %s, verified against the store", db_path)


def store_db_key_for_new_store(db_path: Path, key: str) -> None:
    """Record the key for a store that is being created, before the file exists.

    The one case where no verification is possible, and so the one case a caller has to name
    explicitly. Nothing that opens an existing store may reach this: it is the *creation* path, and
    ``init_store`` follows it with a reopen-and-read before reporting success.
    """
    accounts.write(accounts.DB_KEY, db_path, key)
    logger.info("Assurance store key recorded for new store at %s", db_path)
