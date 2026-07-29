"""Application-level read-model DTOs shared across ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(frozen=True)
class ReadModelVersion:
    generation: int
    etag: str


class EntityContextConnection(TypedDict):
    artifact_id: str
    source: str
    target: str
    conn_type: str
    version: str
    status: str
    path: str
    content_text: str
    associated_entities: list[str]
    src_multiplicity: str
    tgt_multiplicity: str
    specialization: str
    source_name: str
    target_name: str
    source_artifact_type: str
    target_artifact_type: str
    source_domain: str
    target_domain: str
    source_scope: str
    target_scope: str
    other_entity_id: str
    direction: str


class EntityContextCounts(TypedDict):
    conn_in: int
    conn_out: int
    conn_sym: int


class EntityContextReadModel(TypedDict):
    entity: dict[str, Any]
    connections: dict[str, list[EntityContextConnection]]
    counts: EntityContextCounts
    generation: int
    etag: str
