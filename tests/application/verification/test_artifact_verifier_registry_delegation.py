"""Delegation tests for ``ArtifactRegistry.get_entity``/``get_connection``.

These were missing from the facade even though ``VerifierStorePort`` already declares them
(other call sites reached through to ``registry._store`` directly instead) — added for the
viewpoint-application verifier rule, which needs to resolve placed entities/connections.
Regression: the viewpoint rule's own resolution helpers
(``resolve_placed_entities``/``resolve_placed_connections``) exercise this through the public
facade, not the private store.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

_ENTITY = EntityRecord(
    artifact_id="STK@1.x.a", artifact_type="stakeholder", name="Stakeholder", version="1.0.0",
    status="active", domain="test", subdomain="", path=Path("dummy.md"), keywords=(), extra={}, content_text="",
    display_blocks={}, display_label="Stakeholder", display_alias="Stakeholder",
)
_CONNECTION = ConnectionRecord(
    artifact_id="REL@1.x.a", source="STK@1.x.a", target="GOAL@1.x.b", conn_type="archimate-realization",
    version="1.0.0", status="active", path=Path("dummy.outgoing.md"), extra={}, content_text="",
)


class _FakeStore:
    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return _ENTITY if artifact_id == _ENTITY.artifact_id else None

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return _CONNECTION if artifact_id == _CONNECTION.artifact_id else None


def test_get_entity_delegates_to_store() -> None:
    registry = ArtifactRegistry(_FakeStore())
    entity = registry.get_entity("STK@1.x.a")
    assert entity is not None
    assert entity.artifact_type == "stakeholder"
    assert registry.get_entity("UNKNOWN@1.x.a") is None


def test_get_connection_delegates_to_store() -> None:
    registry = ArtifactRegistry(_FakeStore())
    connection = registry.get_connection("REL@1.x.a")
    assert connection is not None
    assert connection.conn_type == "archimate-realization"
    assert registry.get_connection("UNKNOWN@1.x.a") is None
