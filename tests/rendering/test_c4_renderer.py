from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.diagram_types.c4.renderer import C4PumlRenderer
from src.domain.ontology_representation.artifact_types import ConnectionRecord


class _FakeQuery:
    """Minimal ModelQuery for renderer tests."""

    def __init__(self, entities: dict[str, object], connections: list[ConnectionRecord]) -> None:
        self._entities = entities
        self._connections = {c.artifact_id: c for c in connections}

    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def connection_ids(self) -> set[str]:
        return set(self._connections)

    def get_entity(self, artifact_id: str):
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


def _entity(entity_id: str, name: str, artifact_type: str = "application-component", display_alias: str = "") -> object:
    from tests.application.derivation._fixtures import _entity as _make  # noqa: PLC0415
    e = _make(entity_id, artifact_type)
    # Patch name and display_alias on the frozen record by creating a modified copy
    import dataclasses  # noqa: PLC0415
    return dataclasses.replace(e, name=name, display_alias=display_alias)


def _connection(artifact_id: str, source: str, target: str, conn_type: str, content_text: str) -> ConnectionRecord:
    from tests.application.derivation._fixtures import _connection as _make  # noqa: PLC0415
    conn = _make(artifact_id, source, target, conn_type)
    import dataclasses  # noqa: PLC0415
    return dataclasses.replace(conn, content_text=content_text)


def _renderer(
    scope_entity_type: str,
    scope_render_mode: str,
    internal_entity_types: list[str],
    person_archimate_types: frozenset[str] = frozenset(),
) -> C4PumlRenderer:
    return C4PumlRenderer(
        {
            "c4": {
                "scope_entity_type": scope_entity_type,
                "scope_render_mode": scope_render_mode,
                "internal_entity_types": internal_entity_types,
            }
        },
        person_archimate_types=person_archimate_types,
    )


def test_system_context_renders_scope_and_model_relationship(monkeypatch) -> None:
    query = _FakeQuery(
        entities={
            "BUS@1.user": _entity("BUS@1.user", "Customer", artifact_type="business-actor", display_alias="P_Cust01"),
            "APP@1.system": _entity("APP@1.system", "Ordering System", display_alias="SS_Order1"),
            "APP@1.payments": _entity("APP@1.payments", "Payments", display_alias="SS_Paymt"),
        },
        connections=[
            _connection(
                "BUS@1.user---APP@1.system@@archimate-access",
                "BUS@1.user",
                "APP@1.system",
                "archimate-access",
                "Uses the ordering workflow",
            ),
        ],
    )
    monkeypatch.setattr("src.infrastructure.artifact_index.shared_artifact_index", lambda roots: query)

    renderer = _renderer(
        "software-system", "node", [],
        person_archimate_types=frozenset({"business-actor"}),
    )
    puml = renderer.render_body(
        "Ordering Context",
        [],
        [],
        "c4-system-context",
        Path("/tmp"),
        diagram_entities={"_scope_entity_id": "APP@1.system"},
    )

    # Person uses Person_Ext macro (C4-PlantUML stdlib) — person glyph + coloured box.
    # Customer is a business-actor OUTSIDE the system scope → Person_Ext.
    assert 'Person_Ext(P_Cust01, "Customer")' in puml
    assert "actor" not in puml
    assert 'System(SS_Order1, "Ordering System")' in puml
    assert "[[" not in puml
    assert "!include <C4/C4_Component>" in puml
    # Model-backed C4 edges use short, direction-consistent type-default verbs; the
    # connection's prose description stays on the model connection, not the diagram.
    assert "P_Cust01 --> SS_Order1 : accesses" in puml
    assert "Uses the ordering workflow" not in puml


def test_container_view_renders_scope_as_boundary_and_collects_references() -> None:
    renderer = _renderer("software-system", "boundary", ["container"])

    diagram_entities = {
        "software-system": [{"id": "ordering", "entity_id": "APP@1.system", "scope": True, "label": "Ordering System"}],
        "container": [
            {"id": "api", "entity_id": "APP@1.api", "label": "API", "technology": "FastAPI"},
            {"id": "db", "entity_id": "APP@1.db", "label": "Database", "technology": "PostgreSQL"},
        ],
    }
    diagram_connections = [{"source": "api", "target": "db", "label": "Reads and writes orders"}]

    puml = renderer.render_body(
        "Ordering Containers",
        [],
        [],
        "c4-container",
        Path("/tmp"),
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
    )
    refs = renderer.collect_references(
        "c4-container",
        Path("/tmp"),
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
    )

    assert 'System_Boundary(SS_ordering_0, "Ordering System") {' in puml
    # FastAPI has no db/queue keyword → generic Container; PostgreSQL → ContainerDb
    assert 'Container(C_api_0, "API", "FastAPI")' in puml
    assert 'ContainerDb(C_db_1, "Database", "PostgreSQL")' in puml
    assert "Reads and writes orders" in puml
    assert refs.entity_ids == ()  # standalone mode: no model entity tracking
    assert refs.connection_ids == ()
