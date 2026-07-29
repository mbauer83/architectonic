from __future__ import annotations

from typing import Literal

from src.application.ports import ReadableArtifactStore
from src.application.read_models import EntityContextConnection
from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord

from ._combined_support import dispatch_both, merge_sorted, sum_count_dicts, sum_tuple


class CombinedGraphMixin:
    """RelationshipGraph — connections never span repos (GRF proxy guarantee), so every
    method here is a plain concat/merge/sum; the SQLite-backed subset dispatches
    concurrently via the shared executor (REQ@1782080517.IIl8-4)."""

    _engagement: ReadableArtifactStore
    _enterprise: ReadableArtifactStore

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[EntityContextConnection]:
        left, right = dispatch_both(
            lambda store: store.candidate_connections_for_entities(entity_ids), self._engagement, self._enterprise
        )
        return sorted([*left, *right], key=lambda r: r["artifact_id"])

    def connection_counts(self) -> dict[str, tuple[int, int, int]]:
        left, right = dispatch_both(lambda store: store.connection_counts(), self._engagement, self._enterprise)
        return sum_count_dicts(left, right)

    def connection_counts_for(self, entity_id: str) -> tuple[int, int, int]:
        left, right = dispatch_both(
            lambda store: store.connection_counts_for(entity_id), self._engagement, self._enterprise
        )
        return sum_tuple(left, right)

    def connection_counts_for_entities(
        self, entity_ids: list[str] | set[str] | frozenset[str]
    ) -> dict[str, tuple[int, int, int]]:
        left, right = dispatch_both(
            lambda store: store.connection_counts_for_entities(entity_ids), self._engagement, self._enterprise
        )
        return sum_count_dicts(left, right)

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        left, right = dispatch_both(
            lambda store: store.list_connections_by_types(types), self._engagement, self._enterprise
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def list_connections_by_types_for_entities(
        self,
        types: frozenset[str],
        entity_ids: list[str] | set[str] | frozenset[str],
    ) -> list[ConnectionRecord]:
        left, right = dispatch_both(
            lambda store: store.list_connections_by_types_for_entities(types, entity_ids),
            self._engagement,
            self._enterprise,
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        left, right = dispatch_both(
            lambda store: store.find_connections_for(entity_id, direction=direction, conn_type=conn_type),
            self._engagement,
            self._enterprise,
        )
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        left = self._engagement.diagrams_referencing_artifact(artifact_id)
        right = self._enterprise.diagrams_referencing_artifact(artifact_id)
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def grf_references_to_entity(self, artifact_id: str) -> list[EntityRecord]:
        left = self._engagement.grf_references_to_entity(artifact_id)
        right = self._enterprise.grf_references_to_entity(artifact_id)
        return merge_sorted(left, right, lambda r: r.artifact_id)

    def find_neighbors(
        self,
        entity_id: str,
        *,
        max_hops: int = 1,
        conn_type: str | None = None,
    ) -> dict[str, set[str]]:
        left, right = dispatch_both(
            lambda store: store.find_neighbors(entity_id, max_hops=max_hops, conn_type=conn_type),
            self._engagement,
            self._enterprise,
        )
        out = {key: set(value) for key, value in left.items()}
        for key, value in right.items():
            out.setdefault(key, set()).update(value)
        return out
