"""Confidential-store capability sentinel (adapter-agnostic after SC-1).

Adding this sentinel to `registered_names` before the assurance ontology module
is evaluated allows `is_module_enabled` to satisfy
`requires: ["confidential_store"]` — a pure name-based capability signal.

The sentinel's `enabled` property probes whether the configured backend is
available (key/credentials present + store file/endpoint reachable). If either
condition fails, the capability is unavailable and the assurance module will not
be registered (fail-closed).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_SERVICE_NAME = "arch-assurance"


def _store_available(workspace_root: Path) -> bool:
    """Return True if the configured backend appears ready to unlock."""
    try:
        from src.config.storage_settings import storage_assurance_store_backend  # noqa: PLC0415

        backend = storage_assurance_store_backend()
    except (ValueError, Exception):  # noqa: BLE001
        return False

    if backend == "sqlcipher":
        return _sqlcipher_available(workspace_root)
    if backend == "pocketbase":
        return _pocketbase_available()
    if backend == "private-git":
        return _private_git_available(workspace_root)
    return False


def _sqlcipher_available(workspace_root: Path) -> bool:
    try:
        # Use the credential-store abstraction (not raw keyring) so the same backend the
        # store was initialised with is consulted — e.g. the headless Fernet vault on CI,
        # where a raw keyring/SecretService probe would fail on a missing session D-Bus.
        from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

        db_path = workspace_root / ".arch-assurance" / "store.db"
        if not accounts.present(accounts.DB_KEY, db_path):
            return False
    except Exception:  # noqa: BLE001
        return False
    return db_path.exists()


def _pocketbase_available() -> bool:
    import os  # noqa: PLC0415

    return bool(os.getenv("ARCH_POCKETBASE_URL"))


def _private_git_available(workspace_root: Path) -> bool:
    try:
        from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

        repo_scope = workspace_root / ".arch-assurance-git"
        if not accounts.present(accounts.GIT_KEY, repo_scope):
            # Plain (unencrypted) private-git: check repo dir exists
            repo_path = workspace_root / ".arch-assurance-git"
            return repo_path.exists() and (repo_path / "nodes").exists()
    except Exception:  # noqa: BLE001
        return False
    repo_path = workspace_root / ".arch-assurance-git"
    return repo_path.exists()


class _ConfidentialStoreCapability:
    """Synthetic 'module' that satisfies the confidential_store capability dep.

    Not an OntologyModule — never registered as one. Only its `.name` and
    `.enabled` are consumed by `is_module_enabled` during bootstrap.
    """

    name = "confidential_store"
    requires: list[str] = []

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root
        self._available: bool | None = None

    @property
    def enabled(self) -> bool:
        if self._available is None:
            self._available = _store_available(self._workspace_root)
            if not self._available:
                logger.info(
                    "confidential_store: unavailable for configured backend at %s. "
                    "Run `arch-assurance init` to enable.",
                    self._workspace_root,
                )
        return self._available


@lru_cache(maxsize=None)
def make_capability(db_path: Path) -> _ConfidentialStoreCapability:
    """Construct capability sentinel. db_path is interpreted as workspace root.

    Cached per `db_path` for the process's lifetime: the underlying probe
    (`_store_available`) can shell out to a real credential backend (e.g. the WSL2 DPAPI
    bridge spawns `powershell.exe`), which is both expensive and, under many concurrent
    callers (parallel test workers each building a fresh `ModuleRegistry`), prone to
    transient failures — without this cache, two probes in the very same process could
    legitimately disagree, which is what made `build_module_registry()`'s confidential_store
    detection appear flaky under `pytest -n auto`. `get_module_registry()` already caches
    the whole registry the same way for the long-running backend process; this brings ad
    hoc `build_module_registry()` callers (tests, one-off CLI probes) in line with that.
    """
    workspace_root = db_path.parent.parent if db_path.name == "store.db" else db_path.parent
    return _ConfidentialStoreCapability(workspace_root)
