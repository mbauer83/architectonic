"""Shared test fixtures for viewpoint projection-service tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot


def entity(**kw: object) -> EntityRecord:
    defaults: dict[str, object] = dict(
        artifact_id="ENT@A",
        artifact_type="application-component",
        name="A",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="A",
        display_alias="",
    )
    defaults.update(kw)
    return EntityRecord(**defaults)  # type: ignore[arg-type]


def connection(**kw: object) -> ConnectionRecord:
    defaults: dict[str, object] = dict(
        artifact_id="CON@001",
        source="ENT@A",
        target="ENT@B",
        conn_type="archimate-serving",
        version="1.0",
        status="draft",
        path=Path("/fake/conn.md"),
        extra={},
        content_text="",
    )
    defaults.update(kw)
    return ConnectionRecord(**defaults)  # type: ignore[arg-type]


@dataclass
class Store:
    """Fake ``RepositoryReadAccess``/``CriteriaReadAccess``: structurally identical to the
    slice of ``ArtifactIndex``/``ArtifactRegistry`` the projection service reads."""

    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)
    enterprise_ids: frozenset[str] = frozenset()

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(
        self, entity_id: str, *, direction: Literal["any", "outbound", "inbound"] = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        return [c for c in self.connections if c.source == entity_id or c.target == entity_id]

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return next((c for c in self.connections if c.artifact_id == artifact_id), None)

    def entity_ids(self) -> set[str]:
        return set(self.entities)

    def enterprise_entity_ids(self) -> set[str]:
        return set(self.enterprise_ids)

    def engagement_entity_ids(self) -> set[str]:
        return set(self.entities) - set(self.enterprise_ids)

    def connection_ids(self) -> set[str]:
        return {item.artifact_id for item in self.connections}

    def enterprise_connection_ids(self) -> set[str]:
        return set()

    def engagement_connection_ids(self) -> set[str]:
        return self.connection_ids()


REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component", "process"}),
    known_connection_types=frozenset({"archimate-serving"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={},
)
