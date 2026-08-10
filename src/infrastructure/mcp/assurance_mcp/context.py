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
from typing import NamedTuple

from src.application.assurance.ports import (
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


def assurance_workspace_root() -> Path:
    """The workspace the assurance bundle is keyed on, and which locates the non-SQLCipher backends.

    Still a source-tree literal, and deliberately not switched to `manifest.workspace_root` in the same
    breath as the store path was. It decides two things a store cannot be moved away from safely: where a
    `private-git` backend's repository lives, and — through `_credential_scope_path` — the **hash the
    credential account name is derived from**. Repointing it would rename the account holding an existing
    key, which is the key-loss shape, so it is a migration rather than a fix.

    Public, because the capability sentinel must resolve the *same* root the bundle does. It did agree by
    coincidence — both derived a source tree — and the sentinel's move to the manifest would have broken
    that for a deployment with both a deployment root and a private-git backend. One function is how they
    agree on purpose instead.
    """
    return Path(__file__).resolve().parents[4]


def _workspace_root() -> Path:
    return assurance_workspace_root()


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


#: How the ``analysis_id`` served by :meth:`AssuranceContext.exposed_graph` is described to callers.
#: It lives beside the method that implements the scoping rather than in either tool module, because
#: the sentence and the behaviour are one thing: change what scoping does and the description to
#: change is the adjacent one. Its three readers (``assurance_stats`` in ``read_tools``,
#: ``assurance_coverage`` and ``assurance_risk_register`` in ``dashboard_tools``) span two modules,
#: so no tool module could own it without one importing the other for a string.
#: The completeness profiles say it in their own words — ``read_tools._SCOPED_TO_ONE_ANALYSIS`` —
#: because their reason is specific to a profile being defined per unit of work.
ANALYSIS_SCOPE_HINT = (
    " Pass `analysis_id` to ask this of one analysis rather than the whole store: a store holding"
    " several otherwise answers with a total belonging to none of them in particular."
)


class ExposedGraph(NamedTuple):
    """The nodes and edges one session may see, as a pair that cannot be read the wrong way round.

    Two same-typed lists returned positionally are two lists a caller can swap silently, and every
    consumer here passes them straight on as ``(nodes, edges)``. Naming the fields makes the swap a
    type error while still unpacking as a tuple at the call sites that only want to forward them.
    """

    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]


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

    def exposed_graph(self, *, analysis_id: str | None = None) -> ExposedGraph:
        """The store's nodes and edges as this session may see them — optionally one analysis' worth.

        Three whole-store dashboard reads (``assurance_stats``, ``assurance_coverage``,
        ``assurance_risk_register``) each assembled this themselves, in the same four lines. Nothing
        held the copies equal, and none of them offered the ``analysis_id`` the store has taken all
        along — so an agent could ask for a risk register or a coverage gap list of the whole store
        and never of the analysis those registers are read per.

        **Scoping is by node, and the edges follow.** ``analysis_id`` narrows the nodes, and the edge
        filter keeps only edges whose *both* endpoints survived, so an edge leaving the analysis is
        excluded without a second filter — the same mechanism that already hides an edge into a
        node withheld by the classification ceiling. There is no ``analysis_id`` on ``list_edges``
        and there should not be: an edge belongs to an analysis by way of its endpoints.

        The withheld count is dropped deliberately. These three reads are aggregates, and reporting
        "3 withheld" beside a total is how a count of what the ceiling hides leaks out of it.
        """
        from src.application.assurance.exposure import AssuranceExposurePolicy  # noqa: PLC0415

        # `True` rather than `is_available()`: every caller has already gated on it, and asking the
        # store again would be a second unlock round-trip to learn what it just answered.
        policy = AssuranceExposurePolicy(self.max_classification, True)
        nodes, _withheld = policy.filter_nodes(self.store.list_nodes(analysis_id=analysis_id))
        node_ids = frozenset(str(node["node_id"]) for node in nodes)
        return ExposedGraph(nodes, policy.filter_edges(self.store.list_edges(), node_ids))

    def locked_response(self) -> dict[str, object]:
        """The refusal every assurance tool can answer, in the shape every MCP refusal uses."""
        from src.infrastructure.mcp.assurance_mcp import _refusals  # noqa: PLC0415

        return _refusals.store_locked()

    def not_found_response(self, node_id: str) -> dict[str, object]:
        from src.infrastructure.mcp.assurance_mcp import _refusals  # noqa: PLC0415

        return _refusals.not_found(node_id)

    def withheld_response(self, node_id: str, tlp: str) -> dict[str, object]:
        from src.infrastructure.mcp.assurance_mcp import _refusals  # noqa: PLC0415

        return _refusals.classification_ceiling_exceeded(node_id, tlp, self.max_classification)


_CTX = AssuranceContext()


def get_assurance_context() -> AssuranceContext:
    return _CTX


def clear_context_cache() -> None:
    """Evict the factory cache. Used in tests and after backend config changes."""
    from src.infrastructure.assurance.store_factory import clear_factory_cache  # noqa: PLC0415

    clear_factory_cache()
