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


def _store_available(db_path: Path, workspace_root: Path) -> bool:
    """Return True if the configured backend appears ready to unlock.

    Two paths, because two backends locate themselves differently and neither is derivable from the
    other: SQLCipher is a *file* the deployment manifest names, and private-git is a repository under the
    workspace. Deriving one from the other is what this used to do, and it meant the manifest's
    `ARCH_ASSURANCE_DB_PATH` could point the store somewhere the probe never looked.
    """
    try:
        from src.config.storage_settings import storage_assurance_store_backend  # noqa: PLC0415

        backend = storage_assurance_store_backend()
    except (ValueError, Exception):  # noqa: BLE001
        return False

    if backend == "sqlcipher":
        return _sqlcipher_available(db_path)
    if backend == "pocketbase":
        return _pocketbase_available()
    if backend == "private-git":
        return _private_git_available(workspace_root)
    return False


def _sqlcipher_available(db_path: Path) -> bool:
    """The database the manifest names — not a filename re-derived from a workspace root.

    It was `workspace_root / ".arch-assurance" / "store.db"`, which is the default *and* the reason a
    deployment that moved its store had its capability probed at the old address. The credential account
    is scoped to this path too, so getting it wrong asks the wrong question twice.
    """
    try:
        # Use the credential-store abstraction (not raw keyring) so the same backend the
        # store was initialised with is consulted — e.g. the headless Fernet vault on CI,
        # where a raw keyring/SecretService probe would fail on a missing session D-Bus.
        from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415

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

    def __init__(self, db_path: Path, workspace_root: Path) -> None:
        self._db_path = db_path
        self._workspace_root = workspace_root
        self._available: bool | None = None

    @property
    def db_path(self) -> Path:
        """The store this sentinel is about. Readable so a caller can log or assert what was resolved."""
        return self._db_path

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def enabled(self) -> bool:
        if self._available is None:
            self._available = _store_available(self._db_path, self._workspace_root)
            if not self._available:
                logger.info(
                    "confidential_store: unavailable for configured backend at %s. "
                    "Run `arch-assurance init` to enable.",
                    self._db_path,
                )
        return self._available


@lru_cache(maxsize=None)
def make_capability(db_path: Path, workspace_root: Path) -> _ConfidentialStoreCapability:
    """Construct the capability sentinel for a *resolved* store location.

    Both arguments come from the deployment manifest, and both are passed rather than derived. The
    previous signature took only `db_path` and recovered a workspace root from it with
    `db_path.parent.parent` — a round-trip that silently assumed the default layout, so a store moved by
    `ARCH_ASSURANCE_DB_PATH` or a settings key was probed where it used to be.

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
    return _ConfidentialStoreCapability(db_path, workspace_root)


def capability_for_deployment() -> _ConfidentialStoreCapability:
    """The sentinel for wherever *this* deployment keeps its store, per the manifest.

    One home, because both callers wanted the same thing and neither should be deriving it.
    `app_bootstrap` computed a literal from the source tree; `signal_attribute_capability` already asked
    `default_db_path()` — the manifest — and had its correct answer thrown away by `make_capability`'s
    `db_path.parent.parent` round-trip. Two callers, one right and one wrong, and the round-trip made
    them agree on the wrong one.

    **The two arguments come from two places, and that is not an oversight.** The store path is the
    manifest's, because the factory opens exactly that file and `ARCH_ASSURANCE_DB_PATH` must move both.
    The workspace root is `assurance_workspace_root()`, because that is what the *bundle* is keyed on and
    what locates a `private-git` repository and the credential account's scope hash — so the probe and the
    thing it probes cannot disagree.

    Taking the workspace from `manifest.workspace_root` instead was the obvious symmetry and would have
    been a regression: on a deployment with both a deployment root and a private-git backend the manifest
    says `<root>/workspace` while the bundle still uses the source tree, so the capability would report on
    a repository nothing opens. They agreed by coincidence before — both derived a source tree — and one
    shared function is how they agree on purpose. Moving that root is its own migration; see
    `assurance_workspace_root`.
    """
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415
    from src.infrastructure.mcp.assurance_mcp.context import assurance_workspace_root  # noqa: PLC0415

    return make_capability(resolve_manifest().assurance_db_path.path, assurance_workspace_root())
