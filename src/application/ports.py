from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol

from src.application.read_models import EntityContextConnection, EntityContextReadModel, ReadModelVersion
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
)
from src.domain.repository.repo_scope import MountScope


@dataclass(frozen=True)
class Candidate:
    """A file candidate resolved from the identity multimap."""

    artifact_id: str
    path: Path
    scope: MountScope


@dataclass(frozen=True)
class ResolvedArtifact:
    """Result of a canonical artifact resolution, tolerating slug drift."""

    requested_id: str
    canonical_id: str
    path: Path
    renamed: bool
    stale_slug: str | None


class AmbiguousArtifactError(ValueError):
    """Raised when a short stable ID maps to multiple files with no unique scope selection."""


class ArtifactIdentityResolver(Protocol):
    """Stable-id multimap query and per-entity reconciliation."""

    def find_all_by_stable_id(self, short: str) -> list[Candidate]: ...
    def reconcile_short_id(self, short: str) -> None: ...
    def scan_duplicate_short_ids(self) -> dict[str, list[Path]]: ...


class ArtifactLookup(Protocol):
    """Point-lookup by artifact ID."""

    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...
    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...
    def get_diagram(self, artifact_id: str) -> DiagramRecord | None: ...
    def get_document(self, artifact_id: str) -> DocumentRecord | None: ...
    def read_artifact(
        self,
        artifact_id: str,
        *,
        mode: Literal["summary", "full"] = "summary",
        section: str | None = None,
    ) -> dict[str, object] | None: ...
    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None: ...
    def read_entity_context(self, artifact_id: str) -> EntityContextReadModel | None: ...
    def find_file_by_id(self, artifact_id: str) -> Path | None: ...
    def stats(self) -> dict[str, object]: ...


class ArtifactSearch(Protocol):
    """Filtered list queries and full-text search."""

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[EntityRecord]: ...

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[ConnectionRecord]: ...

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DiagramRecord]: ...

    def list_documents(
        self,
        *,
        doc_type: str | None = None,
        status: str | None = None,
        group: str | None = None,
    ) -> list[DocumentRecord]: ...

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
    ) -> list[ArtifactSummary]: ...

    def search_fts(
        self,
        query: str,
        *,
        limit: int,
        include_entities: bool = True,
        include_connections: bool = True,
        include_diagrams: bool = True,
        include_documents: bool = True,
        excluded_entity_types: frozenset[str] = frozenset(),
    ) -> list[tuple[str, str, float]]: ...

    def find_entity_by_workspace_id(
        self,
        artifact_id: str,
        *,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> EntityRecord | None: ...

    def find_entities_by_name(
        self,
        name: str,
        *,
        artifact_type: str | None = None,
        scope: Literal["both", "engagement", "enterprise"] = "both",
    ) -> list[EntityRecord]: ...

    def diagrams_referencing_type_id(self, type_id: str) -> list[tuple[str, str, str]]: ...


class RelationshipGraph(Protocol):
    """Connection graph traversal and candidate queries."""

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]: ...
    def connection_counts(self) -> dict[str, tuple[int, int, int]]: ...
    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]: ...
    def connection_counts_for_entities(
        self, entity_ids: list[str] | set[str] | frozenset[str]
    ) -> dict[str, tuple[int, int, int]]: ...
    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]: ...
    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ) -> list[ConnectionRecord]: ...
    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]: ...
    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]: ...
    def grf_references_to_entity(self, artifact_id: str) -> list[EntityRecord]: ...
    def find_neighbors(
        self,
        entity_id: str,
        *,
        max_hops: int = 1,
        conn_type: str | None = None,
    ) -> dict[str, set[str]]: ...


class RepositoryScopeResolver(Protocol):
    """Repository mount enumeration, scope classification, and artifact status."""

    @property
    def repo_mounts(self) -> list[RepoMount]: ...
    @property
    def repo_roots(self) -> list[Path]: ...
    @property
    def repo_root(self) -> Path: ...
    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]: ...
    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]: ...
    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]: ...
    def entity_status(self, artifact_id: str) -> str | None: ...
    def entity_statuses(self) -> dict[str, str]: ...
    def connection_status(self, artifact_id: str) -> str | None: ...


class ArtifactIndexLifecycle(Protocol):
    """Index read-model versioning, refresh, and ID-membership sets."""

    def refresh(self) -> None: ...
    def read_model_version(self) -> ReadModelVersion: ...
    def entity_ids(self) -> set[str]: ...
    def connection_ids(self) -> set[str]: ...
    def enterprise_entity_ids(self) -> set[str]: ...
    def engagement_entity_ids(self) -> set[str]: ...
    def enterprise_connection_ids(self) -> set[str]: ...
    def engagement_connection_ids(self) -> set[str]: ...
    def enterprise_document_ids(self) -> set[str]: ...
    def enterprise_diagram_ids(self) -> set[str]: ...


class ArtifactMutationObserver(Protocol):
    """Notification when repository files change on disk."""

    def apply_file_changes(self, paths: list[Path]) -> ReadModelVersion: ...


class ArtifactStorePort(
    ArtifactLookup,
    ArtifactSearch,
    RelationshipGraph,
    RepositoryScopeResolver,
    ArtifactIndexLifecycle,
    ArtifactIdentityResolver,
    ArtifactMutationObserver,
    Protocol,
):
    """Full composite artifact store port.

    Prefer narrow sub-contracts where the consumer only needs a subset.
    """


class ReadableArtifactStore(
    ArtifactLookup,
    ArtifactSearch,
    RelationshipGraph,
    RepositoryScopeResolver,
    ArtifactIndexLifecycle,
    ArtifactIdentityResolver,
    Protocol,
):
    """Read-side artifact store without mutation notifications."""


class VerifierStorePort(
    ArtifactLookup,
    ArtifactIndexLifecycle,
    ArtifactIdentityResolver,
    RelationshipGraph,
    RepositoryScopeResolver,
    Protocol,
):
    """Narrowed port for verifier/registry consumers."""


@dataclass(frozen=True)
class ArtifactParsers:
    """Injectable parser callables — swap out for lightweight fakes in tests."""

    parse_entity: Callable[[Path, Path], EntityRecord | None]
    parse_outgoing: Callable[[Path], list[ConnectionRecord]]
    parse_diagram: Callable[[Path], DiagramRecord | None]
    parse_document: Callable[[Path], DocumentRecord | None]

    @staticmethod
    def default(domain_names: frozenset[str]) -> "ArtifactParsers":
        import functools

        from src.application.artifacts.parsing import (
            parse_diagram,
            parse_document,
            parse_entity,
            parse_outgoing_file,
        )

        return ArtifactParsers(
            parse_entity=functools.partial(parse_entity, domain_names=domain_names),
            parse_outgoing=parse_outgoing_file,
            parse_diagram=parse_diagram,
            parse_document=parse_document,
        )
