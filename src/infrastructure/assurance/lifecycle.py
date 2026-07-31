"""Assurance store lifecycle operations: init, unlock, backup, export, rotate-key.

These are called by the `arch-assurance` CLI. They are pure functions that
operate on a store path and the OS credential store.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
from pathlib import Path

from src.domain.clock import utc_now_compact, utc_now_iso
from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import _db_key_guard
from src.infrastructure.assurance._schema import (
    ASSURANCE_PRAGMAS_SQL,
    ASSURANCE_SCHEMA_MIGRATIONS,
    ASSURANCE_SCHEMA_SQL,
    SCHEMA_VERSION,
)
from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

logger = logging.getLogger(__name__)

# Account names and their path scoping live in `_credential_accounts`; this module names the
# secrets it handles and always passes the store path they belong to.


def default_store_path(workspace_root: Path) -> Path:
    return workspace_root / ".arch-assurance" / "store.db"


# ── init ──────────────────────────────────────────────────────────────────────


def init_store(db_path: Path, *, force: bool = False) -> dict[str, object]:
    """Initialise a new confidential assurance store.

    - Generates a 256-bit random key and stores it in the OS keychain.
    - Creates the SQLCipher DB at db_path with the full schema.
    - Saves a recovery key (hex-encoded) in the keychain under a separate account.
    - Adds db_path to .gitignore if possible.

    Returns a dict with status info. Raises if the store already exists and
    force=False.
    """
    import sqlcipher3  # type: ignore[import-untyped]



    if db_path.exists() and not force:
        raise FileExistsError(
            f"Assurance store already exists at {db_path}. "
            "Use --force to reinitialise (this DESTROYS all existing data)."
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)

    key = secrets.token_hex(32)
    recovery_key = secrets.token_hex(32)

    # Scoped to this db_path, so initialising a store here cannot reach the key of a store
    # anywhere else — including the recovery key, which is written in the same breath and so was
    # previously destroyed by the very operation it exists to insure against.
    #
    # Written *before* the old file is removed. The credential store is the step that can fail for
    # reasons outside this process — the key files are deliberately chmod-protected, and that
    # protection has stopped a write before — and removing the database first meant such a failure
    # left neither a store nor a key. In this order it leaves the previous store exactly as it was.
    _db_key_guard.store_db_key_for_new_store(db_path, key)
    accounts.write(accounts.RECOVERY_KEY, db_path, recovery_key)

    if db_path.exists():
        db_path.unlink()

    conn = sqlcipher3.connect(str(db_path))
    conn.execute(f"PRAGMA key = '{key}'")
    conn.executescript(ASSURANCE_PRAGMAS_SQL)
    conn.executescript(ASSURANCE_SCHEMA_SQL)
    for migration_sql in ASSURANCE_SCHEMA_MIGRATIONS:
        try:
            conn.execute(migration_sql)
        except Exception as _exc:  # noqa: BLE001
            if "duplicate column" not in str(_exc):
                raise
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", SCHEMA_VERSION),
    )
    conn.commit()
    conn.close()

    # Re-open with a fresh connection to verify the stored key actually decrypts
    # the DB before we return success. Catches any key-storage round-trip issues.
    conn2 = sqlcipher3.connect(str(db_path))
    conn2.execute(f"PRAGMA key = '{key}'")
    try:
        conn2.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception as exc:
        conn2.close()
        db_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Assurance store was written but cannot be re-opened with the generated key. "
            "This indicates a keyring round-trip issue. "
            "Run `arch-assurance init --force` again."
        ) from exc
    conn2.close()

    _add_to_gitignore(db_path.parent)

    logger.info("Assurance store initialised at %s", db_path)
    return {
        "status": "initialised",
        "db_path": str(db_path),
        "schema_version": SCHEMA_VERSION,
        "recovery_key_in_keychain": accounts.scoped_account(accounts.RECOVERY_KEY, db_path),
        "note": "Recovery key stored in OS keychain. Export it with `arch-assurance export-key`.",
    }


def _add_to_gitignore(directory: Path) -> None:
    gitignore = directory / ".gitignore"
    entry = "*.db\n*.db-wal\n*.db-shm\n"
    if gitignore.exists():
        existing = gitignore.read_text()
        if "*.db" not in existing:
            gitignore.write_text(existing + entry)
    else:
        gitignore.write_text(entry)


# ── backup ────────────────────────────────────────────────────────────────────


def backup_store(db_path: Path, *, backup_path: Path | None = None) -> dict[str, object]:
    """Copy the encrypted DB file to a backup location."""
    if not db_path.exists():
        raise FileNotFoundError(f"No store at {db_path}. Run `arch-assurance init` first.")
    if backup_path is None:
        ts = utc_now_compact()
        backup_path = db_path.parent / f"store.backup.{ts}.db"
    shutil.copy2(db_path, backup_path)
    logger.info("Assurance store backed up to %s", backup_path)
    return {"status": "backed_up", "backup_path": str(backup_path)}


# ── export ────────────────────────────────────────────────────────────────────


# Top-level bundle keys that are AUTHORED seed metadata, not store state (see
# cli/_seed_commands.py) — export_bundle does not produce them, so a plain re-export
# would silently clobber them. They are carried over from an existing target bundle.
_AUTHORED_BUNDLE_KEYS = ("signal_anchors",)


def _authored_metadata(output_path: Path) -> dict[str, object]:
    if not output_path.exists():
        return {}
    try:
        existing = json.loads(output_path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(existing, dict):
        return {}
    return {key: existing[key] for key in _AUTHORED_BUNDLE_KEYS if key in existing}


def export_store(store: SQLCipherAssuranceStore, output_path: Path) -> dict[str, object]:
    """Export the full assurance graph (analyses, nodes, edges, arch-refs) to a JSON file.

    Authored-only bundle keys (``signal_anchors`` — seed metadata the store does not hold)
    are preserved from an existing target bundle so a plain re-export never silently
    clobbers hand-authored seed metadata.
    """
    from src.infrastructure.assurance._portability import export_bundle  # noqa: PLC0415

    data: dict[str, object] = {
        "export_time": utc_now_iso(),
        **_authored_metadata(output_path),
        **export_bundle(store),
    }
    output_path.write_text(json.dumps(data, indent=2))
    logger.info("Assurance store exported to %s", output_path)
    nodes = data["nodes"]
    node_count = len(nodes) if isinstance(nodes, list) else 0
    return {"status": "exported", "output_path": str(output_path), "node_count": node_count}


def import_store(store: SQLCipherAssuranceStore, input_path: Path, *, replace: bool = False) -> dict[str, object]:
    """Restore an exported JSON bundle into *store*, preserving ids (inverse of export_store)."""
    from src.infrastructure.assurance._portability import import_bundle  # noqa: PLC0415

    bundle = json.loads(input_path.read_text())
    counts = import_bundle(store, bundle, replace=replace)
    logger.info("Assurance store imported from %s: %s", input_path, counts)
    return {"status": "imported", "input_path": str(input_path), "counts": counts}


# ── rotate-key ────────────────────────────────────────────────────────────────


def rotate_key(db_path: Path) -> dict[str, object]:
    """Generate a new encryption key and re-encrypt the DB in place (REKEY).

    Every step is verified before the credential is replaced, because this function is the one
    place that can destroy the only key a store has.

    It used to run ``PRAGMA rekey`` and then write the new key unconditionally: no read to confirm
    the old key still opened the store, no reopen to confirm the rekey took, no copy of the file it
    was rewriting. So if the stored key was *already* wrong — which is how every one of the key-loss
    incidents on this codebase begins — the rekey was a silent no-op and the write replaced the last
    correct credential with a random one. The store then held ciphertext no key on the machine
    could open, and the operation reported success.

    Now: verify the old key opens the store, copy the file aside, rekey, reopen with the new key,
    and only then write it. Any failure leaves the credential and the file as they were.
    """
    import sqlcipher3  # type: ignore[import-untyped]

    old_key = accounts.read(accounts.DB_KEY, db_path)
    if old_key is None:
        raise RuntimeError("Current key not found in credential store.")

    # 1. The stored key must actually open the store. `PRAGMA key` alone proves nothing — SQLCipher
    #    defers the check to the first page read — so this reads.
    probe = sqlcipher3.connect(str(db_path))
    try:
        probe.execute(f"PRAGMA key = '{old_key}'")
        probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception as exc:
        probe.close()
        raise RuntimeError(
            f"Refusing to rotate: the stored key does not open {db_path}. Rotating would replace "
            "the only credential that could, and this store is already unopenable — recover it "
            f"before rotating. ({exc})"
        ) from exc
    probe.close()

    # 2. A copy before the file is rewritten. A rekey interrupted midway leaves a database that
    #    neither key opens, and this is the only artefact that survives that.
    backup = str(backup_store(db_path)["backup_path"])

    new_key = secrets.token_hex(32)
    conn = sqlcipher3.connect(str(db_path))
    try:
        conn.execute(f"PRAGMA key = '{old_key}'")
        conn.execute(f"PRAGMA rekey = '{new_key}'")
    finally:
        conn.close()

    # 3. The guard re-proves the new key against the rewritten file before it becomes the stored
    #    one, and refuses otherwise. Until it passes, the credential store still holds a key that
    #    works. Routed through `_db_key_guard` rather than checked here so that *every* writer of
    #    this credential meets the same condition — the class, not this instance of it.
    try:
        _db_key_guard.store_db_key_for_rekey(db_path, new_key)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Rekey did not take, so the new key has NOT been stored and the existing one is "
            f"untouched. A copy of the file from before the rekey is at {backup}. ({exc})"
        ) from exc
    logger.info("Assurance store key rotated successfully")
    return {"status": "key_rotated", "pre_rotation_backup": backup}


# ── export-key ────────────────────────────────────────────────────────────────


def export_recovery_key(db_path: Path) -> dict[str, object]:
    """Return the recovery key from the keychain (for safe offline storage).

    Takes the store path because the account is scoped to it: without that, "the recovery key" is
    ambiguous on a machine holding more than one store, and the ambiguity is what let one store's
    initialisation overwrite another's.
    """
    recovery_key = accounts.read(accounts.RECOVERY_KEY, db_path)
    if recovery_key is None:
        raise RuntimeError("Recovery key not found in credential store.")
    return {
        "recovery_key": recovery_key,
        "warning": "Store this key securely offline. It can restore access if the credential store is lost.",
    }
