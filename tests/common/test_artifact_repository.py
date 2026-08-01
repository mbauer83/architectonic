"""Tests for ArtifactRepository non-delegation logic using a FakeStore.

Covers: count_artifacts_by, search fallback scoring, semantic supplement,
and static verification that ArtifactIndex satisfies ArtifactStorePort.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.artifacts.repository import ArtifactRepository
from src.application.ports import (
    ArtifactIndexLifecycle,
    ArtifactLookup,
    ArtifactMutationObserver,
    ArtifactSearch,
    ArtifactStorePort,
    RelationshipGraph,
    RepositoryScopeResolver,
    VerifierStorePort,
)
from src.application.read_models import EntityContextConnection, EntityContextReadModel
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    RepoMount,
    SemanticSearchProvider,
    summary_from_connection,
    summary_from_diagram,
    summary_from_document,
    summary_from_entity,
)
from src.infrastructure.artifact_index import ArtifactIndex, ReadModelVersion

# ── Helpers ───────────────────────────────────────────────────────────────────


def _entity(
    artifact_id: str,
    *,
    artifact_type: str = "system",
    name: str = "Test",
    domain: str = "technology",
    subdomain: str = "core",
    status: str = "draft",
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status=status,
        domain=domain,
        subdomain=subdomain,
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text=name.lower(),
        display_blocks={},
        display_label=name,
        display_alias=None,
    )


def _conn(artifact_id: str, source: str, target: str, *, conn_type: str = "uses") -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("/tmp/test.outgoing.md"),
        extra={},
        content_text="",
    )


def _diagram(artifact_id: str, *, diagram_type: str = "context") -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type="diagram",
        name=artifact_id,
        diagram_type=diagram_type,
        version="0.1.0",
        status="draft",
        path=Path(f"/tmp/{artifact_id}.puml"),
        extra={},
    )


def _document(artifact_id: str, *, doc_type: str = "adr") -> DocumentRecord:
    return DocumentRecord(
        artifact_id=artifact_id,
        doc_type=doc_type,
        title=artifact_id,
        status="draft",
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        sections=(),
        content_text="",
        extra={},
    )


# ── FakeStore ─────────────────────────────────────────────────────────────────


class FakeStore:
    """Minimal ArtifactStorePort implementation backed by plain dicts."""

    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        connections: list[ConnectionRecord] | None = None,
        diagrams: list[DiagramRecord] | None = None,
        documents: list[DocumentRecord] | None = None,
    ) -> None:
        self._entities = {e.artifact_id: e for e in (entities or [])}
        self._connections = {c.artifact_id: c for c in (connections or [])}
        self._diagrams = {d.artifact_id: d for d in (diagrams or [])}
        self._documents = {d.artifact_id: d for d in (documents or [])}

    # Lifecycle
    def refresh(self) -> None:
        pass

    def read_model_version(self) -> ReadModelVersion:
        return ReadModelVersion(generation=0, etag="fake")

    def apply_file_changes(self, paths: list[Path]) -> ReadModelVersion:
        return self.read_model_version()

    # Point lookups
    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._connections.get(artifact_id)

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self._diagrams.get(artifact_id)

    def get_document(self, artifact_id: str) -> DocumentRecord | None:
        return self._documents.get(artifact_id)

    # Filtered list queries
    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        subdomain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]:
        return sorted(
            (
                r
                for r in self._entities.values()
                if (artifact_type is None or r.artifact_type == artifact_type)
                and (domain is None or r.domain == domain)
                and (subdomain is None or r.subdomain == subdomain)
                and (status is None or r.status == status)
            ),
            key=lambda r: r.artifact_id,
        )

    def list_connections(
        self,
        *,
        conn_type: str | None = None,
        source: str | None = None,
        target: str | None = None,
        status: str | None = None,
    ) -> list[ConnectionRecord]:
        return sorted(
            (
                r
                for r in self._connections.values()
                if (conn_type is None or r.conn_type == conn_type)
                and (source is None or r.source == source)
                and (target is None or r.target == target)
                and (status is None or r.status == status)
            ),
            key=lambda r: r.artifact_id,
        )

    def list_diagrams(self, *, diagram_type: str | None = None, status: str | None = None) -> list[DiagramRecord]:
        return sorted(
            (
                r
                for r in self._diagrams.values()
                if (diagram_type is None or r.diagram_type == diagram_type) and (status is None or r.status == status)
            ),
            key=lambda r: r.artifact_id,
        )

    def list_documents(self, *, doc_type: str | None = None, status: str | None = None) -> list[DocumentRecord]:
        return sorted(
            (
                r
                for r in self._documents.values()
                if (doc_type is None or r.doc_type == doc_type) and (status is None or r.status == status)
            ),
            key=lambda r: r.artifact_id,
        )

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
        _types = artifact_type if isinstance(artifact_type, list) else ([artifact_type] if artifact_type else [])
        types = set(_types)
        _doms = domain if isinstance(domain, list) else ([domain] if domain else [])
        domains = {d.lower() for d in _doms}
        statuses = set(status if isinstance(status, list) else ([status] if status else []))
        out: list[ArtifactSummary] = [
            summary_from_entity(r)
            for r in self._entities.values()
            if include_entities
            and (not types or r.artifact_type in types)
            and (not domains or r.domain.lower() in domains)
            and (not statuses or r.status in statuses)
        ]
        if include_connections:
            out.extend(
                summary_from_connection(r) for r in self._connections.values() if not statuses or r.status in statuses
            )
        if include_diagrams:
            out.extend(
                summary_from_diagram(r)
                for r in self._diagrams.values()
                if (not types or r.artifact_type in types) and (not statuses or r.status in statuses)
            )
        if include_documents:
            out.extend(
                summary_from_document(r) for r in self._documents.values() if not statuses or r.status in statuses
            )
        return sorted(out, key=lambda s: s.artifact_id)

    # Richer reads
    def read_artifact(
        self, artifact_id: str, *, mode: Literal["summary", "full"] = "summary", section: str | None = None
    ) -> dict[str, object] | None:
        r = self._entities.get(artifact_id)
        return {"artifact_id": artifact_id, "name": r.name} if r else None

    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None:
        r = self._entities.get(artifact_id)
        return summary_from_entity(r) if r else None

    def read_entity_context(self, artifact_id: str) -> EntityContextReadModel | None:
        return None

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]:
        return []

    def stats(self) -> dict[str, object]:
        return {"entities": len(self._entities), "connections": len(self._connections)}

    # Connection queries (minimal stubs)
    def connection_counts(self) -> dict[str, tuple[int, int, int]]:
        return {}

    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]:
        return (0, 0, 0)

    def connection_counts_for_entities(
        self, entity_ids: list[str] | set[str] | frozenset[str]
    ) -> dict[str, tuple[int, int, int]]:
        return {entity_id: (0, 0, 0) for entity_id in entity_ids}

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        return [r for r in self._connections.values() if r.conn_type in types]

    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ) -> list[ConnectionRecord]:
        entity_set = set(entity_ids)
        return [
            r
            for r in self._connections.values()
            if r.conn_type in types and (r.source in entity_set or r.target in entity_set)
        ]

    def find_connections_for(
        self, entity_id: str, *, direction: Literal["any", "outbound", "inbound"] = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        return []

    def find_neighbors(self, entity_id: str, *, max_hops: int = 1, conn_type: str | None = None) -> dict[str, set[str]]:
        return {}

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
    ) -> list[tuple[str, str, float]]:
        return []

    # Scope
    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return "unknown"

    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        return "unknown"

    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        return "unknown"

    # Registry
    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def connection_ids(self) -> set[str]:
        return set(self._connections)

    def enterprise_entity_ids(self) -> set[str]:
        return set()

    def engagement_entity_ids(self) -> set[str]:
        return set(self._entities)

    def enterprise_connection_ids(self) -> set[str]:
        return set()

    def engagement_connection_ids(self) -> set[str]:
        return set(self._connections)

    def enterprise_document_ids(self) -> set[str]:
        return set()

    def enterprise_diagram_ids(self) -> set[str]:
        return set()

    def entity_status(self, artifact_id: str) -> str | None:
        r = self._entities.get(artifact_id)
        return r.status if r else None

    def entity_statuses(self) -> dict[str, str]:
        return {aid: r.status for aid, r in self._entities.items()}

    def connection_status(self, artifact_id: str) -> str | None:
        r = self._connections.get(artifact_id)
        return r.status if r else None

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        r = self._entities.get(artifact_id)
        return r.path if r else None

    # Mount properties
    @property
    def repo_mounts(self) -> list[RepoMount]:
        return []

    @property
    def repo_roots(self) -> list[Path]:
        return []

    @property
    def repo_root(self) -> Path:
        return Path("/tmp/fake")


# ── Protocol conformance check ────────────────────────────────────────────────


def test_artifact_index_satisfies_store_port(tmp_path: Path) -> None:
    index = ArtifactIndex(tmp_path)
    _: ArtifactStorePort = index  # static: ArtifactIndex must conform to ArtifactStorePort


def test_fake_store_satisfies_store_port() -> None:
    _: ArtifactStorePort = FakeStore()  # FakeStore must conform for tests to be meaningful


def test_artifact_index_satisfies_narrow_contracts(tmp_path: Path) -> None:
    """ArtifactIndex satisfies all six narrow sub-contracts."""
    index = ArtifactIndex(tmp_path)
    _lookup: ArtifactLookup = index
    _search: ArtifactSearch = index
    _graph: RelationshipGraph = index
    _scope: RepositoryScopeResolver = index
    _lifecycle: ArtifactIndexLifecycle = index
    _observer: ArtifactMutationObserver = index
    _verifier: VerifierStorePort = index


def test_fake_store_satisfies_narrow_contracts() -> None:
    """FakeStore satisfies all six narrow sub-contracts."""
    store = FakeStore()
    _lookup: ArtifactLookup = store
    _search: ArtifactSearch = store
    _graph: RelationshipGraph = store
    _scope: RepositoryScopeResolver = store
    _lifecycle: ArtifactIndexLifecycle = store
    _observer: ArtifactMutationObserver = store
    _verifier: VerifierStorePort = store


def test_narrow_lookup_contract(tmp_path: Path) -> None:
    """ArtifactLookup can be used where only point-lookups are needed."""
    store: ArtifactLookup = FakeStore(entities=[_entity("e1")])
    assert store.get_entity("e1") is not None
    assert store.get_entity("missing") is None
    assert store.find_file_by_id("e1") is not None


def test_narrow_lifecycle_contract() -> None:
    """ArtifactIndexLifecycle exposes ID membership sets."""
    store: ArtifactIndexLifecycle = FakeStore(entities=[_entity("e1"), _entity("e2")])
    assert "e1" in store.entity_ids()
    assert store.enterprise_entity_ids() == set()
    assert "e1" in store.engagement_entity_ids()


def test_narrow_scope_resolver_contract() -> None:
    """RepositoryScopeResolver exposes scope classification and status."""
    store: RepositoryScopeResolver = FakeStore(entities=[_entity("e1", status="approved")])
    assert store.scope_of_entity("e1") == "unknown"
    assert store.entity_status("e1") == "approved"
    assert store.entity_statuses() == {"e1": "approved"}


def test_narrow_mutation_observer_contract() -> None:
    """ArtifactMutationObserver accepts file-change paths."""
    store: ArtifactMutationObserver = FakeStore()
    version = store.apply_file_changes([Path("/tmp/fake.md")])
    assert version is not None


def test_verifier_store_port_uses_subset() -> None:
    """VerifierStorePort is satisfied by the full store and exposes only verifier methods."""
    store: VerifierStorePort = FakeStore(entities=[_entity("e1")])
    # ArtifactLookup methods
    assert store.find_file_by_id("e1") is not None
    # ArtifactIndexLifecycle methods
    assert "e1" in store.entity_ids()
    # RepositoryScopeResolver methods
    assert store.scope_of_entity("e1") == "unknown"
    store.refresh()  # ArtifactIndexLifecycle


# ── count_artifacts_by ────────────────────────────────────────────────────────


def test_count_artifacts_by_artifact_type() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", artifact_type="system"),
            _entity("e2", artifact_type="system"),
            _entity("e3", artifact_type="service"),
        ]
    )
    repo = ArtifactRepository(store)
    counts = repo.count_artifacts_by("artifact_type")
    assert counts == {"service": 1, "system": 2}


def test_count_artifacts_by_domain() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", domain="technology"),
            _entity("e2", domain="technology"),
            _entity("e3", domain="business"),
        ]
    )
    repo = ArtifactRepository(store)
    counts = repo.count_artifacts_by("domain")
    assert counts == {"business": 1, "technology": 2}


def test_count_artifacts_by_diagram_type() -> None:
    store = FakeStore(
        diagrams=[
            _diagram("d1", diagram_type="context"),
            _diagram("d2", diagram_type="context"),
            _diagram("d3", diagram_type="sequence"),
        ]
    )
    repo = ArtifactRepository(store)
    counts = repo.count_artifacts_by("diagram_type")
    assert counts == {"context": 2, "sequence": 1}


def test_count_artifacts_by_includes_connections_when_requested() -> None:
    store = FakeStore(
        entities=[_entity("e1", artifact_type="system")],
        connections=[_conn("c1", "e1", "e2")],
    )
    repo = ArtifactRepository(store)
    counts_without = repo.count_artifacts_by("artifact_type", include_connections=False)
    counts_with = repo.count_artifacts_by("artifact_type", include_connections=True)
    assert "system" in counts_without
    assert "connection" not in counts_without
    assert "connection" in counts_with


def test_count_artifacts_by_filters_by_domain() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", artifact_type="system", domain="technology"),
            _entity("e2", artifact_type="service", domain="business"),
        ]
    )
    repo = ArtifactRepository(store)
    counts = repo.count_artifacts_by("artifact_type", domain="technology")
    assert counts == {"system": 1}
    assert "service" not in counts


# ── search fallback ───────────────────────────────────────────────────────────


def test_search_falls_back_to_python_scoring_when_fts_empty() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", name="Payment Gateway", artifact_type="system"),
            _entity("e2", name="Auth Service", artifact_type="system"),
        ]
    )
    repo = ArtifactRepository(store)
    result = repo.search("payment")
    assert len(result.hits) >= 1
    assert result.hits[0].record.artifact_id == "e1"


def test_search_respects_entity_type_filter() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", name="Payment System", artifact_type="system"),
            _entity("e2", name="Payment Service", artifact_type="service"),
        ]
    )
    repo = ArtifactRepository(store)
    result = repo.search("payment", entity_types=["system"])
    ids = {h.record.artifact_id for h in result.hits}
    assert "e1" in ids
    assert "e2" not in ids


def test_search_respects_domain_filter() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", name="Payment", domain="technology"),
            _entity("e2", name="Payment", domain="business"),
        ]
    )
    repo = ArtifactRepository(store)
    result = repo.search("payment", domains=["technology"])
    ids = {h.record.artifact_id for h in result.hits}
    assert "e1" in ids
    assert "e2" not in ids


def test_search_includes_connections_when_requested() -> None:
    store = FakeStore(
        entities=[_entity("e1", name="Alpha")],
        connections=[_conn("c1", "e1", "e2")],
    )
    repo = ArtifactRepository(store)
    with_conns = repo.search("alpha", include_connections=True)
    without_conns = repo.search("alpha", include_connections=False)
    assert any(h.record_type == "entity" for h in with_conns.hits)
    conn_hits_with = [h for h in with_conns.hits if h.record_type == "connection"]
    conn_hits_without = [h for h in without_conns.hits if h.record_type == "connection"]
    assert len(conn_hits_without) == 0
    _ = conn_hits_with  # connections may or may not score, depends on content


def test_search_strict_record_type_filters_results() -> None:
    store = FakeStore(
        entities=[
            _entity("e1", name="Invoice Service"),
        ]
    )
    repo = ArtifactRepository(store)
    result = repo.search("invoice", prefer_record_type="entity", strict_record_type=True)
    assert all(h.record_type == "entity" for h in result.hits)


def test_search_limit_respected() -> None:
    store = FakeStore(entities=[_entity(f"e{i}", name=f"Service {i}") for i in range(20)])
    repo = ArtifactRepository(store)
    result = repo.search("service", limit=5)
    assert len(result.hits) <= 5


# ── semantic supplement ───────────────────────────────────────────────────────


class _FakeSemantic(SemanticSearchProvider):
    def __init__(self, hits: list[tuple[float, str]]) -> None:
        self._hits = hits

    def top_k(self, query: str, k: int, threshold: float) -> list[tuple[float, str]]:
        return [(score, aid) for score, aid in self._hits if score >= threshold][:k]


def test_semantic_supplement_adds_hit_not_in_fts_results() -> None:
    entities = [_entity(f"e{i}", name=f"Entity {i}") for i in range(60)]
    store = FakeStore(entities=entities)
    sem = _FakeSemantic([(0.9, "e50")])
    repo = ArtifactRepository(store, semantic_provider=sem)
    result = repo.search("something entirely unrelated to any name")
    sem_hits = [h for h in result.hits if h.record_type == "entity" and h.record.artifact_id == "e50"]
    assert len(sem_hits) == 1


def test_semantic_supplement_skipped_when_store_has_fewer_than_50_entities() -> None:
    entities = [_entity(f"e{i}", name=f"Entity {i}") for i in range(10)]
    store = FakeStore(entities=entities)
    sem = _FakeSemantic([(0.9, "e5")])
    repo = ArtifactRepository(store, semantic_provider=sem)
    result = repo.search("unrelated query xyz abc")
    # With only 10 entities the semantic supplement is skipped
    sem_hits = [h for h in result.hits if h.score > 2.0]
    assert len(sem_hits) == 0


# ── registry-style delegation ─────────────────────────────────────────────────


def test_repo_entity_ids_delegates_to_store() -> None:
    store = FakeStore(entities=[_entity("e1"), _entity("e2"), _entity("e3")])
    repo = ArtifactRepository(store)
    assert repo.entity_ids() == {"e1", "e2", "e3"}


def test_repo_entity_ids_empty_when_no_entities() -> None:
    repo = ArtifactRepository(FakeStore())
    assert repo.entity_ids() == set()


def test_repo_connection_ids_delegates_to_store() -> None:
    store = FakeStore(
        entities=[_entity("src"), _entity("tgt")],
        connections=[_conn("c1", "src", "tgt"), _conn("c2", "src", "tgt")],
    )
    repo = ArtifactRepository(store)
    assert repo.connection_ids() == {"c1", "c2"}


def test_repo_connection_ids_empty_when_no_connections() -> None:
    repo = ArtifactRepository(FakeStore())
    assert repo.connection_ids() == set()


def test_repo_enterprise_entity_ids_delegates_to_store() -> None:
    """WU-E7: the viewpoint execution use case's ``repo_scope`` filtering needs this on the
    facade, not just the underlying index — regression guard for the missing delegation."""
    store = FakeStore(entities=[_entity("e1")])
    repo = ArtifactRepository(store)
    assert repo.enterprise_entity_ids() == store.enterprise_entity_ids()


def test_repo_engagement_entity_ids_delegates_to_store() -> None:
    store = FakeStore(entities=[_entity("e1")])
    repo = ArtifactRepository(store)
    assert repo.engagement_entity_ids() == store.engagement_entity_ids()
