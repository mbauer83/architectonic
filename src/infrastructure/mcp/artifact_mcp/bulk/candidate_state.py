from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

from src.application.artifacts.parsing import parse_diagram, parse_document, parse_entity, parse_outgoing_file
from src.application.ports import ArtifactStorePort, Candidate
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import entity_id_from_path
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)
from src.infrastructure.mcp.artifact_mcp.bulk.candidate_lists import CandidateListMixin
from src.infrastructure.write.artifact_write.staged_workspace import stage_live_path


class CandidateStore(CandidateListMixin):
    def __init__(
        self,
        *,
        live: ArtifactStorePort,
        live_root: Path,
        staged_root: Path,
        touched_paths: set[Path],
        domain_names: frozenset[str],
    ) -> None:
        self._live = live
        self.repo_roots = [staged_root]
        self.repo_root = staged_root
        self.repo_mounts = live.repo_mounts
        self._live_root = live_root.resolve()
        self._staged_root = staged_root.resolve()
        self._entities: dict[str, EntityRecord] = {}
        self._connections: dict[str, ConnectionRecord] = {}
        self._diagrams: dict[str, DiagramRecord] = {}
        self._documents: dict[str, DocumentRecord] = {}
        self._deleted_entities: set[str] = set()
        self._deleted_connections: set[str] = set()
        self._deleted_diagrams: set[str] = set()
        self._deleted_documents: set[str] = set()
        for path in sorted(touched_paths):
            self._absorb_touched_path(path.resolve(), domain_names=domain_names)

    def _absorb_touched_path(self, path: Path, *, domain_names: frozenset[str]) -> None:
        rel = self._rel_from_staged(path)
        if rel is None:
            return
        live_path = self._live_root / rel
        if path.name.endswith(".outgoing.md"):
            self._deleted_connections.update(c.artifact_id for c in parse_outgoing_file(live_path))
            self._connections.update((c.artifact_id, c) for c in parse_outgoing_file(path))
        elif self._is_diagram_path(rel):
            if (old := self._live.get_diagram(live_path.stem)) is not None:
                self._deleted_diagrams.add(old.artifact_id)
            if path.exists() and (new := parse_diagram(path)) is not None:
                self._diagrams[new.artifact_id] = new
        elif self._is_document_path(rel):
            if (old := self._live.get_document(live_path.stem)) is not None:
                self._deleted_documents.add(old.artifact_id)
            if path.exists() and (new := parse_document(path)) is not None:
                self._documents[new.artifact_id] = new
        elif path.suffix == ".md":
            self._deleted_entities.add(entity_id_from_path(live_path))
            model_root = self._model_root_for(path)
            if path.exists() and model_root is not None:
                new = parse_entity(path, model_root, domain_names=domain_names)
                if new is not None:
                    self._entities[new.artifact_id] = new

    def _rel_from_staged(self, path: Path) -> Path | None:
        try:
            return path.relative_to(self._staged_root)
        except ValueError:
            return None

    def _staged_path_for_live(self, path: Path) -> Path:
        try:
            staged_path = self._staged_root / path.resolve().relative_to(self._live_root)
        except ValueError:
            return path
        if path.suffix == ".md" and not path.name.endswith(".outgoing.md"):
            stage_live_path(staged_path.with_suffix(".outgoing.md"), path.with_suffix(".outgoing.md"))
        return stage_live_path(staged_path, path)

    def _model_root_for(self, path: Path) -> Path | None:
        parts = self._rel_from_staged(path)
        if parts is None or MODEL not in parts.parts:
            return None
        idx = parts.parts.index(MODEL)
        return self._staged_root.joinpath(*parts.parts[: idx + 1])

    @staticmethod
    def _is_diagram_path(rel: Path) -> bool:
        return rel.parts[:2] == (DIAGRAM_CATALOG, DIAGRAMS) and rel.suffix in {".puml", ".md"}

    @staticmethod
    def _is_document_path(rel: Path) -> bool:
        return rel.parts[:1] == (DOCS,) and rel.suffix == ".md"

    def _map_entity(self, rec: EntityRecord | None) -> EntityRecord | None:
        return None if rec is None else replace(rec, path=self._staged_path_for_live(rec.path))

    def _map_connection(self, rec: ConnectionRecord | None) -> ConnectionRecord | None:
        return None if rec is None else replace(rec, path=self._staged_path_for_live(rec.path))

    def _map_diagram(self, rec: DiagramRecord | None) -> DiagramRecord | None:
        return None if rec is None else replace(rec, path=self._staged_path_for_live(rec.path))

    def _map_document(self, rec: DocumentRecord | None) -> DocumentRecord | None:
        return None if rec is None else replace(rec, path=self._staged_path_for_live(rec.path))

    def refresh(self) -> None:
        return None

    def read_model_version(self):
        return self._live.read_model_version()

    def entity_ids(self) -> set[str]:
        return (self._live.entity_ids() - self._deleted_entities) | set(self._entities)

    def connection_ids(self) -> set[str]:
        return (self._live.connection_ids() - self._deleted_connections) | set(self._connections)

    def enterprise_entity_ids(self) -> set[str]:
        return (self._live.enterprise_entity_ids() - self._deleted_entities) | set(self._entities)

    def engagement_entity_ids(self) -> set[str]:
        return (self._live.engagement_entity_ids() - self._deleted_entities) | set(self._entities)

    def enterprise_connection_ids(self) -> set[str]:
        return self._live.enterprise_connection_ids() - self._deleted_connections

    def engagement_connection_ids(self) -> set[str]:
        return (self._live.engagement_connection_ids() - self._deleted_connections) | set(self._connections)

    def enterprise_document_ids(self) -> set[str]:
        return self._live.enterprise_document_ids() - self._deleted_documents

    def enterprise_diagram_ids(self) -> set[str]:
        return self._live.enterprise_diagram_ids() - self._deleted_diagrams

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        if artifact_id in self._deleted_entities:
            return None
        return self._entities.get(artifact_id) or self._map_entity(self._live.get_entity(artifact_id))

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        # `_deleted_connections`/`_connections` are always keyed by the canonical
        # (stale-slug-free) connection id — parse_outgoing_file builds every
        # ConnectionRecord.artifact_id that way. A caller may still query with a
        # stale-slug or otherwise non-canonical endpoint form (e.g. a diagram's
        # `connection-ids-used` entry written before a rename), so the query is
        # normalized the same way before either membership check.
        canonical = stable_conn_id(artifact_id)
        if artifact_id in self._deleted_connections or canonical in self._deleted_connections:
            return None
        return (
            self._connections.get(artifact_id)
            or self._connections.get(canonical)
            or self._map_connection(self._live.get_connection(artifact_id))
        )

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        if artifact_id in self._deleted_diagrams:
            return None
        return self._diagrams.get(artifact_id) or self._map_diagram(self._live.get_diagram(artifact_id))

    def get_document(self, artifact_id: str) -> DocumentRecord | None:
        if artifact_id in self._deleted_documents:
            return None
        return self._documents.get(artifact_id) or self._map_document(self._live.get_document(artifact_id))

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        if artifact_id in self._entities:
            return self._entities[artifact_id].path
        if artifact_id in self._connections:
            return self._connections[artifact_id].path
        if artifact_id in self._diagrams:
            return self._diagrams[artifact_id].path
        if artifact_id in self._documents:
            return self._documents[artifact_id].path
        deleted = self._deleted_entities | self._deleted_connections | self._deleted_diagrams | self._deleted_documents
        if artifact_id in deleted:
            return None
        path = self._live.find_file_by_id(artifact_id)
        return self._staged_path_for_live(path) if path is not None else None

    def entity_status(self, artifact_id: str) -> str | None:
        rec = self._entities.get(artifact_id)
        return rec.status if rec is not None else self._live.entity_status(artifact_id)

    def entity_statuses(self) -> dict[str, str]:
        statuses = {k: v for k, v in self._live.entity_statuses().items() if k not in self._deleted_entities}
        statuses.update({k: v.status for k, v in self._entities.items()})
        return statuses

    def connection_status(self, artifact_id: str) -> str | None:
        rec = self._connections.get(artifact_id)
        return rec.status if rec is not None else self._live.connection_status(artifact_id)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        live = [r for r in self._live.find_connections_for(entity_id, direction=direction, conn_type=conn_type)]
        overlay = [r for r in self._connections.values() if _matches_connection(r, entity_id, direction, conn_type)]
        mapped = [self._map_connection(r) for r in live if r.artifact_id not in self._deleted_connections]
        return [r for r in mapped if r is not None] + overlay

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        live = [
            d for d in self._live.diagrams_referencing_artifact(artifact_id)
            if d.artifact_id not in self._deleted_diagrams
        ]
        mapped = [self._map_diagram(d) for d in live]
        return [d for d in mapped if d is not None] + [
            d for d in self._diagrams.values() if _diagram_refs(d, artifact_id)
        ]

    def grf_references_to_entity(self, artifact_id: str) -> list[EntityRecord]:
        live = [
            e for e in self._live.grf_references_to_entity(artifact_id)
            if e.artifact_id not in self._deleted_entities
        ]
        mapped = [self._map_entity(e) for e in live]
        return [e for e in mapped if e is not None] + [
            e for e in self._entities.values() if e.extra.get("global-artifact-id") == artifact_id
        ]

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        rel = self._rel_from_staged(path.resolve())
        return self._live.scope_for_path(self._live_root / rel) if rel is not None else self._live.scope_for_path(path)

    def scope_of_entity(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        path = self.find_file_by_id(artifact_id)
        return self.scope_for_path(path) if path is not None else "unknown"

    def scope_of_connection(self, artifact_id: str) -> Literal["enterprise", "engagement", "unknown"]:
        path = self.find_file_by_id(artifact_id)
        return self.scope_for_path(path) if path is not None else "unknown"

    def find_all_by_stable_id(self, short: str) -> list[Candidate]:
        overlaid = [
            Candidate(aid, rec.path, "engagement")
            for aid, rec in {**self._entities, **self._diagrams, **self._documents}.items()
            if stable_id(aid) == short
        ]
        return overlaid + [
            replace(c, path=self._staged_path_for_live(c.path))
            for c in self._live.find_all_by_stable_id(short)
        ]

    def reconcile_short_id(self, short: str) -> None:
        self._live.reconcile_short_id(short)

    def scan_duplicate_short_ids(self) -> dict[str, list[Path]]:
        return self._live.scan_duplicate_short_ids()

    def read_artifact(
        self,
        artifact_id: str,
        *,
        mode: Literal["summary", "full"] = "summary",
        section: str | None = None,
    ):
        return self._live.read_artifact(artifact_id, mode=mode, section=section)

    def summarize_artifact(self, artifact_id: str) -> ArtifactSummary | None:
        return self._live.summarize_artifact(artifact_id)

    def read_entity_context(self, artifact_id: str):
        return self._live.read_entity_context(artifact_id)

    def stats(self) -> dict[str, object]:
        return self._live.stats()

    def candidate_connections_for_entities(self, entity_ids: list[str]):
        return self._live.candidate_connections_for_entities(entity_ids)

    def connection_counts(self) -> dict[str, tuple[int, int, int]]:
        return self._live.connection_counts()

    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]:
        return self._live.connection_counts_for(entity_id)

    def connection_counts_for_entities(self, entity_ids: list[str] | set[str] | frozenset[str]):
        return self._live.connection_counts_for_entities(entity_ids)

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        return self._live.list_connections_by_types(types)

    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ):
        return self._live.list_connections_by_types_for_entities(types, entity_ids)

    def find_neighbors(self, entity_id: str, *, max_hops: int = 1, conn_type: str | None = None):
        return self._live.find_neighbors(entity_id, max_hops=max_hops, conn_type=conn_type)


def candidate_registry(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> ArtifactRegistry:
    return ArtifactRegistry(candidate_store(live_root=live_root, staged_root=staged_root, touched_paths=touched_paths))


def candidate_store(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> CandidateStore:
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.artifact_index import mutable_artifact_index

    domain_names = build_runtime_catalogs(get_module_registry()).ontology.known_domain_names()
    return CandidateStore(
        live=mutable_artifact_index(live_root),
        live_root=live_root,
        staged_root=staged_root,
        touched_paths=touched_paths,
        domain_names=domain_names,
    )


def _matches_connection(
    rec: ConnectionRecord,
    entity_id: str,
    direction: Literal["any", "outbound", "inbound"],
    conn_type: str | None,
) -> bool:
    return (conn_type is None or rec.conn_type == conn_type) and (
        direction == "any"
        and entity_id in {rec.source, rec.target}
        or direction == "outbound"
        and rec.source == entity_id
        or direction == "inbound"
        and rec.target == entity_id
    )


def _diagram_refs(rec: DiagramRecord, artifact_id: str) -> bool:
    refs = [rec.extra.get(key, []) for key in ("entity-ids-used", "connection-ids-used")]
    return any(isinstance(group, list) and artifact_id in group for group in refs)
