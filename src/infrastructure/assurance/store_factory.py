"""Assurance store/archive/connector factory keyed by workspace (SC-1).

Reads `storage.assurance` config (store_backend, signals_backend) and returns
port-typed instances. Unknown backends fail closed at build time (ValueError at
startup rather than at first use).

Connection sharing:
  - sqlcipher: archive + colocated-signals share the store's SQLCipher connection
    via a conn_factory callable; no `_conn` reference escapes the factory.
  - private-git: archive is EncryptedGitArchive (chain.jsonl + Fernet .enc files);
    shares the store's Fernet key via a fernet_factory lambda.
  - pocketbase: archive uses a plain-SQLite file alongside the assurance dir.

Cache is keyed by resolved workspace path. Call `clear_factory_cache()` in tests.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.application.assurance_ports import AssuranceArchive, ConfidentialAssuranceStore
from src.config import storage_settings
from src.domain.clock import epoch_seconds

#: Backends whose unlock is a key read from the OS credential store, and which therefore
#: participate in auto-unlock. PocketBase is omitted — its auth is session-based.
_KEY_BACKED_STORE_BACKENDS = frozenset({"sqlcipher", "private-git"})

logger = logging.getLogger(__name__)

#: Guards the bundle registry below. Held only for dictionary access — never across a store
#: unlock, which reads the OS credential store and can take seconds. A slow or unreachable
#: credential backend must cost the request that provoked it, not every assurance request in
#: the process.
_lock = threading.Lock()
_instances: dict[str, "_AssuranceBundle"] = {}

#: Guards `_process_authorized` alone. Separate from `_lock` because the two protect unrelated
#: state — one process-wide authorization flag, one workspace-keyed registry — and the unlock
#: path reads the flag while the registry is being populated. Sharing a single non-reentrant
#: lock across both made that read a self-deadlock.
_auth_lock = threading.Lock()

#: How long to wait before re-attempting auto-unlock on a bundle that is still locked.
#: Reading the activation gate costs a credential-backend round trip (a `powershell.exe`
#: subprocess on WSL2), so an unactivated store must not pay for one per request.
AUTO_UNLOCK_RETRY_SECONDS = 30
_last_auto_unlock_attempt: dict[str, int] = {}

#: Whether this process has been explicitly authorized to open the store, for its lifetime.
#: Under the 'manual' activation policy this is what `arch-assurance unlock` grants and `lock`
#: revokes: the keychain gate records that the store was ceremonially activated once, which is a
#: fact about the store, while this records that *this* process may open it, which is not.
#: Deliberately process state with nothing persisted — it dies with the process, which is what
#: makes a restart start locked.
_process_authorized = False


def authorize_process() -> None:
    """Permit this process to open the store, until it exits or authorization is revoked."""
    global _process_authorized  # noqa: PLW0603
    with _auth_lock:
        _process_authorized = True


def revoke_process_authorization() -> None:
    """Withdraw this process's authorization and close any open store immediately.

    Revocation has to take effect on the running process, not at its next start, or `lock`
    would report success while the capability stayed open.

    The flag is cleared before any store is closed, so a request arriving mid-revocation cannot
    reopen what this call has just shut.
    """
    global _process_authorized  # noqa: PLW0603
    with _auth_lock:
        _process_authorized = False
    with _lock:
        bundles = list(_instances.values())
    for bundle in bundles:
        if bundle.store.is_unlocked():
            bundle.store.lock()


def is_process_authorized() -> bool:
    with _auth_lock:
        return _process_authorized


class _AssuranceBundle:
    """Container for the three port-typed assurance adapters."""

    def __init__(
        self,
        store: ConfidentialAssuranceStore,
        archive: AssuranceArchive,
        store_backend: str,
        signals_backend: str,
        archive_backend: str,
        store_scope: Path,
    ) -> None:
        self.store = store
        self.archive = archive
        self.store_backend = store_backend
        self.signals_backend = signals_backend
        self.archive_backend = archive_backend
        #: The path this store's credentials are scoped to. Carried on the bundle because the
        #: startup unlock needs it: the activation gate belongs to one store, not to the machine.
        self.store_scope = store_scope
        # Run/VEX stores exist only where the transactional boundary does
        # (SQLCipher store; the capability predicate denies mutations elsewhere).
        self.snapshot_store = _build_snapshot_store(store, store_backend)
        self.vex_store = _build_vex_store(store, store_backend)


def _build_snapshot_store(store: ConfidentialAssuranceStore, store_backend: str):
    if store_backend != "sqlcipher":
        return None
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

    assert isinstance(store, SQLCipherAssuranceStore)
    return SQLCipherSnapshotStore(store._thread_conn_or_none)  # noqa: SLF001


def _build_vex_store(store: ConfidentialAssuranceStore, store_backend: str):
    if store_backend != "sqlcipher":
        return None
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore

    assert isinstance(store, SQLCipherAssuranceStore)
    return SQLCipherVexAssessmentStore(store._thread_conn_or_none)  # noqa: SLF001


def get_assurance_bundle(
    workspace: Path,
    *,
    db_path: Path | None = None,
    signals_db_path: Path | None = None,
) -> _AssuranceBundle:
    """Return the workspace-keyed assurance bundle, building it on first call.

    Construction happens under the registry lock so concurrent callers share one bundle. The
    unlock attempt deliberately does not: it reads the activation gate from the OS credential
    store, and holding the registry lock across that would serialize every assurance request in
    the process behind one keychain round trip.
    """
    key = str(workspace.resolve())
    with _lock:
        bundle = _instances.get(key)
        if bundle is None:
            bundle = _build_bundle(workspace, db_path=db_path, signals_db_path=signals_db_path)
            _instances[key] = bundle
    _retry_auto_unlock_if_due(key, bundle)
    return bundle


def _retry_auto_unlock_if_due(key: str, bundle: "_AssuranceBundle") -> None:
    """Attempt auto-unlock for a bundle that is still locked, at most once per retry window.

    This is the only auto-unlock path, covering both a freshly built bundle's first attempt and
    later retries. A bundle is cached for the life of the process, so a credential backend that
    was momentarily unreachable at startup would otherwise leave the store locked until a
    restart, however healthy the keychain became afterwards. Retrying widens nothing: the same
    activation gate and the same activation policy decide, and a store that is not activated
    stays locked.

    Must be called *without* the registry lock held. The throttle bookkeeping takes it briefly;
    the unlock attempt itself runs outside it, because that attempt reads the activation gate and
    can block for as long as the credential backend takes.
    """
    if bundle.store_backend not in _KEY_BACKED_STORE_BACKENDS or bundle.store.is_unlocked():
        return
    now = epoch_seconds()
    with _lock:
        if now - _last_auto_unlock_attempt.get(key, 0) < AUTO_UNLOCK_RETRY_SECONDS:
            return
        _last_auto_unlock_attempt[key] = now
    try_auto_unlock(bundle.store, bundle.store_backend, bundle.store_scope)


def clear_factory_cache() -> None:
    """Evict all cached bundles. Use in tests or after backend config changes."""
    with _lock:
        _instances.clear()
        _last_auto_unlock_attempt.clear()


# ── Internal builders ─────────────────────────────────────────────────────────


def _build_bundle(
    workspace: Path,
    *,
    db_path: Path | None,
    signals_db_path: Path | None,
) -> _AssuranceBundle:
    from src.config.storage_settings import (
        storage_assurance_archive_backend,
        storage_assurance_signals_backend,
        storage_assurance_store_backend,
    )

    store_backend = storage_assurance_store_backend()
    signals_backend = storage_assurance_signals_backend()
    archive_backend = storage_assurance_archive_backend()
    if signals_backend == "sqlcipher-colocated" and store_backend != "sqlcipher":
        raise ValueError(
            "signals_backend 'sqlcipher-colocated' requires store_backend 'sqlcipher'. "
            f"Current store_backend: {store_backend!r}"
        )
    assurance_dir = workspace / ".arch-assurance"

    store = _build_store(store_backend, workspace, db_path, assurance_dir)
    archive = _build_archive(store, store_backend, assurance_dir, archive_backend)

    # The bundle is built locked. Opening it is the caller's next step, taken outside the
    # registry lock because it reads the OS credential store.

    logger.info(
        "Assurance bundle: store=%s signals=%s archive=%s",
        store_backend, signals_backend, archive_backend,
    )
    store_scope = _store_scope(store_backend, workspace, db_path, assurance_dir)
    return _AssuranceBundle(
        store, archive, store_backend, signals_backend, archive_backend, store_scope,
    )


def _store_scope(
    store_backend: str, workspace: Path, db_path: Path | None, assurance_dir: Path
) -> Path:
    """The path a backend's credentials are scoped to.

    One path per store, whatever the backend keeps on disk: the SQLCipher database file, the
    private-git repository directory, or — for a backend with nothing local — the assurance
    directory itself, which is still per-workspace and so still distinguishes two deployments.
    """
    if store_backend == "private-git":
        return workspace / ".arch-assurance-git"
    if store_backend == "sqlcipher":
        return db_path if db_path is not None else assurance_dir / "store.db"
    return assurance_dir


def _build_store(
    store_backend: str,
    workspace: Path,
    db_path: Path | None,
    assurance_dir: Path,
) -> ConfidentialAssuranceStore:
    if store_backend == "sqlcipher":
        from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

        return SQLCipherAssuranceStore(db_path or assurance_dir / "store.db")

    if store_backend == "pocketbase":
        return _build_pocketbase_store()

    if store_backend == "private-git":
        repo_path = db_path or workspace / ".arch-assurance-git"
        from src.infrastructure.assurance._encrypted_private_git_store import (
            EncryptedPrivateGitAssuranceStore,
        )

        return EncryptedPrivateGitAssuranceStore(repo_path)

    raise ValueError(  # fail-closed — checked by settings loader, but defensive repeat
        f"Unsupported store_backend: {store_backend!r}"
    )


def _build_archive(
    store: ConfidentialAssuranceStore,
    store_backend: str,
    assurance_dir: Path,
    archive_backend: str,
) -> AssuranceArchive:
    # Cloud-native WORM archives are independent of the store backend.
    if archive_backend == "s3-worm":
        from src.infrastructure.assurance._s3_worm_archive import S3WORMAssuranceArchive

        return S3WORMAssuranceArchive.from_env()

    if archive_backend == "azure-blob-worm":
        from src.infrastructure.assurance._azure_blob_worm_archive import (
            AzureBlobWORMAssuranceArchive,
        )

        return AzureBlobWORMAssuranceArchive.from_env()

    if archive_backend == "worm" and store_backend != "sqlcipher":
        raise ValueError(
            "archive_backend 'worm' requires store_backend 'sqlcipher'. "
            f"Current store_backend: {store_backend!r}"
        )

    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive

    if store_backend == "sqlcipher":
        from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

        assert isinstance(store, SQLCipherAssuranceStore)
        sqlcipher_store = store
        conn_factory = sqlcipher_store._thread_conn_or_none  # noqa: SLF001
        if archive_backend == "worm":
            from src.infrastructure.assurance._worm_archive import WORMSQLCipherAssuranceArchive
            return WORMSQLCipherAssuranceArchive(conn_factory)
        return SQLCipherAssuranceArchive(conn_factory)

    if store_backend == "private-git":
        from src.infrastructure.assurance._encrypted_git_archive import EncryptedGitArchive
        from src.infrastructure.assurance._encrypted_private_git_store import (
            EncryptedPrivateGitAssuranceStore,
        )

        assert isinstance(store, EncryptedPrivateGitAssuranceStore)
        return EncryptedGitArchive(store._repo, fernet_factory=lambda: store._fernet)  # noqa: SLF001

    # Non-SQLCipher/non-private-git backends (pocketbase): plain-SQLite local archive.
    archive_filename = f"{store_backend.replace('-', '_')}_archive.db"
    archive_path = assurance_dir / archive_filename
    return _make_local_sqlite_archive(archive_path)


def try_auto_unlock(
    store: ConfidentialAssuranceStore, store_backend: str, store_scope: Path
) -> None:
    """Open the store on process start when the deployment's policy allows it.

    The "setup-confirmed" keychain entry, written by `arch-assurance unlock`, records that this
    store was ceremonially activated at least once — the recovery-key prompt and conscious
    enablement happened. It says nothing about whether *this* process may open the store
    unattended, which is a deployment question rather than a fact about the store, so the answer
    comes from the configured activation policy:

    * 'manual' (default) — a new process starts locked; `unlock` authorizes the process that is
      running. A restart is already a human act on a workstation, where walk-up access to an
      unattended session is the threat.
    * 'persistent' — a new process opens the store from the gate until `lock` revokes it, so an
      unattended server reboot does not take the capability down.

    Fail-closed throughout: an unreadable policy, absent confirmation, absent key, or any unlock
    error leaves the store locked.

    Each way of not unlocking is reported distinctly, and an *environmental* failure is a
    warning rather than a debug line. A store that was never activated is a normal state worth
    only a hint; a credential backend that could not be reached is a silent loss of the whole
    assurance capability, and reporting it at debug is what once made a locked store look
    inexplicable.
    """
    from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

    try:
        policy = storage_settings.storage_assurance_activation_policy()
    except ValueError as exc:
        logger.warning(
            "Assurance store (%s) not opened on start: %s The store stays locked.",
            store_backend,
            exc,
        )
        return

    if policy != "persistent" and not is_process_authorized():
        logger.info(
            "Assurance store (%s) starts locked under the '%s' activation policy: run "
            "`arch-assurance unlock` to authorize this process, or set "
            "storage.assurance.activation_policy to 'persistent' for an unattended deployment.",
            store_backend,
            policy,
        )
        return

    try:
        confirmed = accounts.read(accounts.SETUP_GATE, store_scope)
    except RuntimeError:
        # No secure credential backend could be resolved. On WSL2 this is usually the
        # `powershell.exe` interop probe failing or exceeding its timeout — transient, but it
        # leaves the store locked, so it must be visible.
        logger.warning(
            "Assurance store (%s) not auto-unlocked: no secure credential backend is reachable, "
            "so the activation gate could not be read. The store stays locked.",
            store_backend,
        )
        return
    except Exception:  # noqa: BLE001
        logger.warning(
            "Assurance store (%s) not auto-unlocked: reading the activation gate failed. "
            "The store stays locked.",
            store_backend,
            exc_info=True,
        )
        return

    if not confirmed:
        logger.info(
            "Assurance store (%s) not auto-unlocked: run `arch-assurance unlock` once to activate.",
            store_backend,
        )
        return

    try:
        store.unlock()
    except RuntimeError:
        # Expected when not yet initialised (key absent) — stays locked.
        logger.info(
            "Assurance store (%s) not auto-unlocked: key absent or store not initialised.",
            store_backend,
        )
        return
    except Exception:  # noqa: BLE001
        logger.warning(
            "Assurance store (%s) auto-unlock failed; store remains locked.",
            store_backend,
            exc_info=True,
        )
        return

    logger.info("Assurance store (%s) auto-unlocked from OS keychain.", store_backend)


def _build_pocketbase_store() -> ConfidentialAssuranceStore:
    import os

    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore

    base_url = os.getenv("ARCH_POCKETBASE_URL", "")
    admin_email = os.getenv("ARCH_POCKETBASE_ADMIN_EMAIL", "")
    admin_password = os.getenv("ARCH_POCKETBASE_ADMIN_PASSWORD", "")
    if not base_url:
        raise RuntimeError(
            "store_backend 'pocketbase' requires ARCH_POCKETBASE_URL env var. "
            "Set it to the PocketBase instance URL (e.g. http://localhost:8090)."
        )
    return PocketBaseAssuranceStore(base_url, admin_email, admin_password)


def _dict_row(cursor: Any, row: Any) -> dict[str, object]:
    return dict(zip([col[0] for col in cursor.description], row))


def _make_local_sqlite_archive(archive_path: Path) -> AssuranceArchive:
    """Lazy plain-SQLite archive for non-SQLCipher backends."""
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
    from src.infrastructure.assurance._schema import ARCHIVE_ONLY_SCHEMA_SQL

    init_lock = threading.Lock()
    conn_holder: list[sqlite3.Connection] = []

    def _get_conn() -> sqlite3.Connection:
        if not conn_holder:
            with init_lock:
                if not conn_holder:
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(str(archive_path))
                    conn.row_factory = _dict_row  # type: ignore[assignment]
                    conn.executescript(ARCHIVE_ONLY_SCHEMA_SQL)
                    conn.commit()
                    conn_holder.append(conn)
        return conn_holder[0]

    return SQLCipherAssuranceArchive(_get_conn)
