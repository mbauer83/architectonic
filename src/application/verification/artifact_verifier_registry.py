from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.ports import AmbiguousArtifactError, ResolvedArtifact, VerifierStorePort
from src.domain.artifact_id import slug_of, stable_id
from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord


class ArtifactRegistry:
    """Verifier/write-oriented facade over the shared model index."""

    def __init__(self, store: VerifierStorePort) -> None:
        self._store = store

    @property
    def repo_roots(self) -> list[Path]:
        return self._store.repo_roots

    def refresh(self) -> None:
        self._store.refresh()

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return self._store.find_file_by_id(artifact_id)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._store.get_entity(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._store.get_connection(artifact_id)

    def entity_ids(self) -> set[str]:
        return self._store.entity_ids()

    def enterprise_entity_ids(self) -> set[str]:
        return self._store.enterprise_entity_ids()

    def enterprise_document_ids(self) -> set[str]:
        return self._store.enterprise_document_ids()

    def enterprise_diagram_ids(self) -> set[str]:
        return self._store.enterprise_diagram_ids()

    def engagement_entity_ids(self) -> set[str]:
        return self._store.engagement_entity_ids()

    def connection_ids(self) -> set[str]:
        return self._store.connection_ids()

    def enterprise_connection_ids(self) -> set[str]:
        return self._store.enterprise_connection_ids()

    def engagement_connection_ids(self) -> set[str]:
        return self._store.engagement_connection_ids()

    def entity_status(self, artifact_id: str) -> str | None:
        return self._store.entity_status(artifact_id)

    def entity_statuses(self) -> dict[str, str]:
        return self._store.entity_statuses()

    def connection_status(self, artifact_id: str) -> str | None:
        return self._store.connection_status(artifact_id)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        return self._store.find_connections_for(entity_id, direction=direction, conn_type=conn_type)

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        return self._store.diagrams_referencing_artifact(artifact_id)

    def grf_references_to_entity(self, artifact_id: str) -> list[EntityRecord]:
        return self._store.grf_references_to_entity(artifact_id)

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return self._store.scope_for_path(path)

    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        return self._store.scope_of_entity(artifact_id)

    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        return self._store.scope_of_connection(artifact_id)

    def resolve_artifact(
        self,
        artifact_id: str,
        *,
        scope: Literal["engagement", "enterprise", "both"] = "both",
    ) -> ResolvedArtifact | None:
        """Resolve an artifact ID tolerating slug drift and cross-mount shadowing.

        Returns None when no live file exists.  Raises AmbiguousArtifactError when
        multiple files share the same stable id and the given scope does not select
        exactly one.
        """
        short = stable_id(artifact_id)

        path = self._store.find_file_by_id(artifact_id)
        if path is not None and path.exists():
            requested_slug = slug_of(artifact_id)
            entity = self._store.get_entity(artifact_id)
            canonical_id = entity.artifact_id if entity is not None else artifact_id
            canonical_slug = slug_of(canonical_id)
            stale_slug = requested_slug if requested_slug != canonical_slug else None
            return ResolvedArtifact(
                requested_id=artifact_id,
                canonical_id=canonical_id,
                path=path,
                renamed=False,
                stale_slug=stale_slug,
            )

        self._store.reconcile_short_id(short)

        candidates = self._store.find_all_by_stable_id(short)
        if scope != "both":
            candidates = [c for c in candidates if c.scope == scope]
        candidates = [c for c in candidates if c.path.exists()]

        if not candidates:
            return None
        if len(candidates) > 1:
            paths = [str(c.path) for c in candidates]
            raise AmbiguousArtifactError(
                f"Stable id {short!r} matches multiple files: {paths}"
            )

        candidate = candidates[0]
        entity = self._store.get_entity(candidate.artifact_id)
        canonical_id = entity.artifact_id if entity is not None else candidate.artifact_id
        requested_slug = slug_of(artifact_id)
        canonical_slug = slug_of(canonical_id)
        stale_slug = requested_slug if requested_slug != canonical_slug else None
        return ResolvedArtifact(
            requested_id=artifact_id,
            canonical_id=canonical_id,
            path=candidate.path,
            renamed=candidate.artifact_id != artifact_id,
            stale_slug=stale_slug,
        )
