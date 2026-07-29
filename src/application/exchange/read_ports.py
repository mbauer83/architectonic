"""Narrow read ports for the exchange import/export use cases (D10, parent plan §4.5,
WU-F3a/F3b): each use case needs only a slice of the full ``ArtifactStorePort`` surface, so
each slice is its own Protocol — independently fakeable in tests, and satisfied structurally
by ``ArtifactRegistry`` without requiring its unrelated methods.
"""

from __future__ import annotations

from typing import Literal, Protocol

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


class EntityLookup(Protocol):
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...


class ConnectionLookup(Protocol):
    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]: ...
