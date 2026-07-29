"""Shared context for assurance MCP tools.

Provides port-typed ConfidentialAssuranceStore, AssuranceArchive, and the
signal-snapshot / VEX signal stores via the store factory (workspace-keyed singleton).
Adapters are selected by `storage.assurance` config; default: SQLCipher store
+ co-located confidential signals.

Exposes `max_classification` (TLP ceiling) and `_exposure_log` for filtering and
logging at the arch-assurance-read boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.assurance_ports import (
    AssuranceArchive,
    ConfidentialAssuranceStore,
    WORMAssuranceArchive,
)

_exposure_log = logging.getLogger("arch-assurance-exposure")

_TLP_ORDER: dict[str, int] = {
    "TLP:WHITE": 0,
    "TLP:GREEN": 1,
    "TLP:AMBER": 2,
    "TLP:RED": 3,
}


def tlp_level(tlp: str) -> int:
    return _TLP_ORDER.get(str(tlp).upper(), 0)


def is_above_ceiling(tlp: str, ceiling: str) -> bool:
    """Return True if tlp is more sensitive than ceiling (should be withheld)."""
    return tlp_level(tlp) > tlp_level(ceiling)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _manifest():  # type: ignore[no-untyped-def]
    """The deployment manifest — one resolver shared with `arch-repair upgrade`
    and Docker startup, so every surface opens the same physical stores."""
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    return resolve_manifest()


def default_db_path() -> Path:
    """Return the deployment-resolved store path (env/settings override or default)."""
    return _manifest().assurance_db_path.path


def default_signals_db_path() -> Path:
    """Return the deployment-resolved signals DB path (env/settings override or default)."""
    return _manifest().signals_db_path.path


class AssuranceContext:
    """Accessor for the shared assurance store, archive, and security connector.

    Return types are the port interfaces (ConfidentialAssuranceStore,
    AssuranceArchive) — no concrete adapter types leak.
    """

    def _bundle(self):  # type: ignore[return]
        from src.infrastructure.assurance.store_factory import get_assurance_bundle  # noqa: PLC0415

        manifest = _manifest()
        return get_assurance_bundle(
            _workspace_root(),
            db_path=manifest.assurance_db_path.path,
            signals_db_path=manifest.signals_db_path.path,
        )

    @property
    def store(self) -> ConfidentialAssuranceStore:
        return self._bundle().store

    @property
    def archive(self) -> AssuranceArchive:
        return self._bundle().archive

    @property
    def snapshot_store(self):  # type: ignore[no-untyped-def] — port-typed at use sites
        """Signal-snapshot reads/mutations; None outside the SQLCipher store."""
        return self._bundle().snapshot_store

    @property
    def vex_store(self):  # type: ignore[no-untyped-def] — port-typed at use sites
        """VEX assessment reads/mutations; None outside the SQLCipher store."""
        return self._bundle().vex_store

    @property
    def store_backend(self) -> str:
        return self._bundle().store_backend

    @property
    def signals_backend(self) -> str:
        return self._bundle().signals_backend

    @property
    def archive_backend(self) -> str:
        return self._bundle().archive_backend

    @property
    def worm_archive(self) -> WORMAssuranceArchive | None:
        """Return the archive as WORMAssuranceArchive when the worm backend is active.

        Returns None when archive_backend is 'standard'. Callers should check for
        None before invoking WORM-specific methods (legal holds, crypto-shredding,
        DEK provisioning, RFC 3161 timestamps).
        """
        archive = self._bundle().archive
        if isinstance(archive, WORMAssuranceArchive):
            return archive
        return None

    @property
    def max_classification(self) -> str:
        """TLP ceiling for MCP exposure control. Reads from config each call."""
        from src.config.storage_settings import storage_assurance_max_classification  # noqa: PLC0415

        return storage_assurance_max_classification()

    def is_available(self) -> bool:
        return self.store.is_unlocked()

    def locked_response(self) -> dict[str, object]:
        return {
            "error": "assurance_store_locked",
            "message": (
                "The confidential assurance store is not unlocked. "
                "Run `arch-assurance unlock` to enable assurance tools."
            ),
        }

    def not_found_response(self, node_id: str) -> dict[str, object]:
        return {"error": "not_found", "node_id": node_id}

    def withheld_response(self, node_id: str, tlp: str) -> dict[str, object]:
        return {
            "error": "classification_ceiling_exceeded",
            "node_id": node_id,
            "tlp": tlp,
            "max_classification": self.max_classification,
            "message": (
                f"Node {node_id} (TLP:{tlp}) exceeds the configured "
                f"max_classification ({self.max_classification}). "
                "Raise the ceiling in storage.assurance.max_classification to access it."
            ),
        }


_CTX = AssuranceContext()


def get_assurance_context() -> AssuranceContext:
    return _CTX


def clear_context_cache() -> None:
    """Evict the factory cache. Used in tests and after backend config changes."""
    from src.infrastructure.assurance.store_factory import clear_factory_cache  # noqa: PLC0415

    clear_factory_cache()
