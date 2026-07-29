"""Shared test fixtures for derivation strategy tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


def _entity(artifact_id: str, artifact_type: str = "application-component") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=artifact_id,
        version="1.0",
        status="approved",
        domain="TEST",
        subdomain="test",
        path=Path(f"/fake/{artifact_id}.yaml"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias="",
    )


def _connection(
    artifact_id: str,
    source: str,
    target: str,
    conn_type: str = "serving",
) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="1.0",
        status="approved",
        path=Path(f"/fake/{artifact_id}.yaml"),
        extra={},
        content_text="",
    )


@dataclass
class FakeQuery:
    """Minimal in-memory ModelQuery for unit tests."""

    _entities: dict[str, EntityRecord]
    _connections: dict[str, ConnectionRecord]

    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        connections: list[ConnectionRecord] | None = None,
    ) -> None:
        self._entities = {e.artifact_id: e for e in (entities or [])}
        self._connections = {c.artifact_id: c for c in (connections or [])}

    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def connection_ids(self) -> set[str]:
        return set(self._connections)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._connections.get(artifact_id)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        result = []
        for conn in self._connections.values():
            if conn_type is not None and conn.conn_type != conn_type:
                continue
            is_source = conn.source == entity_id
            is_target = conn.target == entity_id
            if direction == "outbound" and not is_source:
                continue
            if direction == "inbound" and not is_target:
                continue
            if direction == "any" and not (is_source or is_target):
                continue
            result.append(conn)
        return result
