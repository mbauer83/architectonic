from __future__ import annotations

from pathlib import Path

from src.application.ports import ReadableArtifactStore
from src.application.read_models import ReadModelVersion
from src.domain.ontology_representation.artifact_types import RepoMount

from ._combined_graph import CombinedGraphMixin
from ._combined_lookup import CombinedLookupMixin
from ._combined_scope_identity import CombinedScopeIdentityMixin
from ._combined_search import CombinedSearchMixin
from ._combined_support import EXECUTOR


class CombinedArtifactView(
    CombinedScopeIdentityMixin,
    CombinedLookupMixin,
    CombinedSearchMixin,
    CombinedGraphMixin,
):
    """Stateless read-side composition over two per-root ArtifactIndex aggregate roots.

    Each canonical per-physical-root ArtifactIndex is the aggregate root and consistency
    boundary — it owns its own mem store, SQLite index, and lock, and enforces its own
    invariants under that lock. This view holds no independent mutable state and enforces
    no invariant of its own; it is a pure read-time composition over two existing aggregate
    roots and therefore cannot itself go stale.
    """

    def __init__(self, engagement: ReadableArtifactStore, enterprise: ReadableArtifactStore) -> None:
        self._engagement = engagement
        self._enterprise = enterprise

    def close(self) -> None:
        """Close both sides. A caller holding the view cannot reach the halves to close them itself."""
        self._engagement.close()
        self._enterprise.close()

    def __enter__(self) -> CombinedArtifactView:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def repo_mounts(self) -> list[RepoMount]:
        return [*self._engagement.repo_mounts, *self._enterprise.repo_mounts]

    @property
    def repo_roots(self) -> list[Path]:
        return [*self._engagement.repo_roots, *self._enterprise.repo_roots]

    @property
    def repo_root(self) -> Path:
        raise NotImplementedError("CombinedArtifactView has two repo roots; use repo_roots")

    def refresh(self) -> None:
        left = EXECUTOR.submit(self._engagement.refresh)
        right = EXECUTOR.submit(self._enterprise.refresh)
        left.result()
        right.result()

    def read_model_version(self) -> ReadModelVersion:
        eng = self._engagement.read_model_version()
        ent = self._enterprise.read_model_version()
        return ReadModelVersion(generation=eng.generation + ent.generation, etag=f"{eng.etag}:{ent.etag}")
