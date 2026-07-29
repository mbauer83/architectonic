"""Query/search facade built on top of a readable artifact store."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application._artifact_aggregation import count_artifacts_by as _count_artifacts_by
from src.application._artifact_search import (
    search_artifacts as _search_artifacts,
)
from src.application.document_links import reference_dicts_for_entity
from src.application.ports import ReadableArtifactStore
from src.application.read_models import (
    EntityContextConnection,
    EntityContextReadModel,
    ReadModelVersion,  # noqa: F401
)
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    SearchResult,
    SemanticSearchProvider,
)

_RecordType = Literal["entity", "connection", "diagram", "document"]


class ArtifactRepository:
    """Query/search facade over a ReadableArtifactStore."""

    def __init__(
        self,
        store: ReadableArtifactStore,
        semantic_provider: SemanticSearchProvider | None = None,
        *,
        excluded_entity_types: frozenset[str] = frozenset(),
    ) -> None:
        self._store = store
        self._semantic = semantic_provider
        self._excluded_entity_types = excluded_entity_types

    @property
    def repo_mounts(self) -> list[RepoMount]:
        return self._store.repo_mounts

    @property
    def repo_roots(self) -> list[Path]:
        return self._store.repo_roots

    @property
    def repo_root(self) -> Path:
        return self._store.repo_root

    def refresh(self) -> None:
        self._store.refresh()

    def read_model_version(self) -> ReadModelVersion:
        return self._store.read_model_version()

    def read_entity_context(self, artifact_id: str) -> EntityContextReadModel | None:
        return self._store.read_entity_context(artifact_id)

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]:
        return self._store.candidate_connections_for_entities(entity_ids)

    def entity_ids(self) -> set[str]:
        return self._store.entity_ids()

    def connection_ids(self) -> set[str]:
        return self._store.connection_ids()

    def enterprise_entity_ids(self) -> set[str]:
        return self._store.enterprise_entity_ids()

    def engagement_entity_ids(self) -> set[str]:
        return self._store.engagement_entity_ids()

    def enterprise_connection_ids(self) -> set[str]:
        return self._store.enterprise_connection_ids()

    def engagement_connection_ids(self) -> set[str]:
        return self._store.engagement_connection_ids()

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._store.get_entity(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._store.get_connection(artifact_id)

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self._store.get_diagram(artifact_id)

    def get_document(self, artifact_id: str) -> DocumentRecord | None:
        return self._store.get_document(artifact_id)

    def list_documents(
        self,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DocumentRecord]:
        return self._store.list_documents(doc_type=doc_type, status=status, group=group)

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[EntityRecord]:
        return self._store.list_entities(
            artifact_type=artifact_type,
            domain=domain,
            subdomain=subdomain,
            status=status,
            group=group,
        )

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ConnectionRecord]:
        return self._store.list_connections(
            conn_type=conn_type, source=source, target=target, status=status, group=group
        )

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DiagramRecord]:
        return self._store.list_diagrams(diagram_type=diagram_type, status=status, group=group)

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
        return self._store.list_artifacts(
            artifact_type=artifact_type,
            domain=domain,
            status=status,
            include_entities=include_entities,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
            include_documents=include_documents,
        )

    def read_artifact(
        self,
        artifact_id: str,
        *,
        mode: Literal["summary", "full"] = "summary",
        section: str | None = None,
    ) -> dict[str, object] | None:
        data = self._store.read_artifact(artifact_id, mode=mode, section=section)
        if data is None or data.get("record_type") != "entity":
            return data
        entity = self._store.get_entity(str(data["artifact_id"]))
        if entity is not None:
            data["referenced_in_documents"] = reference_dicts_for_entity(
                documents=self._store.list_documents(),
                entity=entity,
            )
        return data

    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None:
        return self._store.summarize_artifact(artifact_id)

    def stats(self) -> dict[str, object]:
        return self._store.stats()

    def connection_counts(self) -> dict[str, tuple[int, int, int]]:
        return self._store.connection_counts()

    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]:
        return self._store.connection_counts_for(entity_id)

    def connection_counts_for_entities(
        self, entity_ids: list[str] | set[str] | frozenset[str]
    ) -> dict[str, tuple[int, int, int]]:
        return self._store.connection_counts_for_entities(entity_ids)

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        return self._store.list_connections_by_types(types)

    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ) -> list[ConnectionRecord]:
        return self._store.list_connections_by_types_for_entities(types, entity_ids)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        return self._store.find_connections_for(entity_id, direction=direction, conn_type=conn_type)

    def find_neighbors(
        self,
        entity_id: str,
        *,
        max_hops: int = 1,
        conn_type: str | None = None,
    ) -> dict[str, set[str]]:
        return self._store.find_neighbors(entity_id, max_hops=max_hops, conn_type=conn_type)

    def count_artifacts_by(
        self,
        group_by: Literal["artifact_type", "diagram_type", "domain", "group"],
        *,
        artifact_type: str | list[str] | None = None,
        domain: str | list[str] | None = None,
        status: str | list[str] | None = None,
        include_connections: bool = True,
        include_diagrams: bool = True,
    ) -> dict[str, int]:
        return _count_artifacts_by(
            self._store,
            group_by,
            artifact_type=artifact_type,
            domain=domain,
            status=status,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
        )

    def search_artifacts(
        self,
        query: str,
        *,
        limit: int = 10,
        domain: str | list[str] | None = None,
        artifact_type: str | list[str] | None = None,
        include_entities: bool = True,
        include_connections: bool = True,
        include_diagrams: bool = True,
        include_documents: bool = True,
        prefer_record_type: _RecordType | None = None,
        strict_record_type: bool = False,
        excluded_entity_types: frozenset[str] = frozenset(),
    ) -> SearchResult:
        return _search_artifacts(
            self._store,
            self._semantic,
            query,
            limit=limit,
            domain=domain,
            artifact_type=artifact_type,
            include_entities=include_entities,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
            include_documents=include_documents,
            prefer_record_type=prefer_record_type,
            strict_record_type=strict_record_type,
            excluded_entity_types=self._excluded_entity_types | excluded_entity_types,
        )

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return self._store.scope_for_path(path)

    def find_entity_by_workspace_id(
        self,
        artifact_id: str,
        *,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> EntityRecord | None:
        return self._store.find_entity_by_workspace_id(artifact_id, scope=scope)

    def find_entities_by_name(
        self,
        name: str,
        *,
        artifact_type: str | None = None,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> list[EntityRecord]:
        return self._store.find_entities_by_name(name, artifact_type=artifact_type, scope=scope)

    def diagrams_referencing_type_id(self, type_id: str) -> list[tuple[str, str, str]]:
        return self._store.diagrams_referencing_type_id(type_id)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        entity_types: list[str] | None = None,
        domains: list[str] | None = None,
        include_connections: bool = True,
        include_diagrams: bool = True,
        include_documents: bool = True,
        prefer_record_type: _RecordType | None = None,
        strict_record_type: bool = False,
    ) -> SearchResult:
        # Entities are always in for this .search() method.
        return self.search_artifacts(
            query,
            limit=limit,
            domain=domains,
            artifact_type=entity_types,
            include_entities=True,
            include_connections=include_connections,
            include_diagrams=include_diagrams,
            include_documents=include_documents,
            prefer_record_type=prefer_record_type,
            strict_record_type=strict_record_type,
        )
