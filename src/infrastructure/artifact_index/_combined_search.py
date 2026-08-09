from __future__ import annotations

from typing import Literal

from src.application.ports import ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import (
    ALL_SEARCHABLE_KINDS,
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)

from ._combined_support import dispatch_both, first_not_none, merge_search_rows, merge_sorted


class CombinedSearchMixin:
    """ArtifactSearch — global-sort merges for listings, per-kind merge for full-text search."""

    _engagement: ReadableArtifactStore
    _enterprise: ReadableArtifactStore

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[EntityRecord]:
        left = self._engagement.list_entities(
            artifact_type=artifact_type, domain=domain, subdomain=subdomain, status=status, group=group
        )
        right = self._enterprise.list_entities(
            artifact_type=artifact_type, domain=domain, subdomain=subdomain, status=status, group=group
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ConnectionRecord]:
        left = self._engagement.list_connections(
            conn_type=conn_type, source=source, target=target, status=status, group=group
        )
        right = self._enterprise.list_connections(
            conn_type=conn_type, source=source, target=target, status=status, group=group
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DiagramRecord]:
        left = self._engagement.list_diagrams(diagram_type=diagram_type, status=status, group=group)
        right = self._enterprise.list_diagrams(diagram_type=diagram_type, status=status, group=group)
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def list_documents(
        self,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DocumentRecord]:
        left = self._engagement.list_documents(doc_type=doc_type, status=status, group=group)
        right = self._enterprise.list_documents(doc_type=doc_type, status=status, group=group)
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def list_artifacts(
        self,
        *,
        artifact_type: str | list[str] | None = None,
        domain: str | list[str] | None = None,
        status: str | list[str] | None = None,
        include_entities: bool = True,
        include_connections: bool = False,
        include_diagrams: bool = False,
        include_documents: bool = False,
    ) -> list[ArtifactSummary]:
        left = self._engagement.list_artifacts(
            artifact_type=artifact_type,
            domain=domain,
            status=status,
            include_entities=include_entities,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
            include_documents=include_documents,
        )
        right = self._enterprise.list_artifacts(
            artifact_type=artifact_type,
            domain=domain,
            status=status,
            include_entities=include_entities,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
            include_documents=include_documents,
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def search_fts(
        self,
        query: str,
        *,
        limit: int,
        kinds: frozenset[str] = ALL_SEARCHABLE_KINDS,
        excluded_entity_types: frozenset[str] = frozenset(),
    ) -> list[tuple[str, str, float]]:
        def call(store: ReadableArtifactStore) -> list[tuple[str, str, float]]:
            return store.search_fts(
                query,
                limit=limit,
                kinds=kinds,
                excluded_entity_types=excluded_entity_types,
            )

        left, right = dispatch_both(call, self._engagement, self._enterprise)
        return merge_search_rows(left, right, limit=limit)

    def find_entity_by_workspace_id(
        self,
        artifact_id: str,
        *,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> EntityRecord | None:
        match scope:
            case "engagement":
                return self._engagement.find_entity_by_workspace_id(artifact_id, scope="both")
            case "enterprise":
                return self._enterprise.find_entity_by_workspace_id(artifact_id, scope="both")
            case "both":
                return first_not_none(
                    self._engagement.find_entity_by_workspace_id(artifact_id, scope="both"),
                    lambda: self._enterprise.find_entity_by_workspace_id(artifact_id, scope="both"),
                )

    def find_entities_by_name(
        self,
        name: str,
        *,
        artifact_type: str | None = None,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> list[EntityRecord]:
        match scope:
            case "engagement":
                return self._engagement.find_entities_by_name(name, artifact_type=artifact_type, scope="both")
            case "enterprise":
                return self._enterprise.find_entities_by_name(name, artifact_type=artifact_type, scope="both")
            case "both":
                return sorted(
                    [
                        *self._engagement.find_entities_by_name(name, artifact_type=artifact_type, scope="both"),
                        *self._enterprise.find_entities_by_name(name, artifact_type=artifact_type, scope="both"),
                    ],
                    key=lambda r: r.artifact_id,
                )

    def diagrams_referencing_type_id(self, type_id: str) -> list[tuple[str, str, str]]:
        left, right = dispatch_both(
            lambda store: store.diagrams_referencing_type_id(type_id), self._engagement, self._enterprise
        )
        return sorted([*left, *right])
