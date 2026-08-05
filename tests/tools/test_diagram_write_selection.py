from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.diagram_selection import resolve_diagram_selection


def _entity(
    artifact_id: str,
    artifact_type: str,
    name: str,
    *,
    domain: str = "business",
    subdomain: str = "processes",
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain=domain,
        subdomain=subdomain,
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id.replace("@", "_").replace(".", "_").replace("-", "_"),
    )


def _conn(source: str, target: str, conn_type: str = "archimate-flow") -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source}---{target}@@{conn_type}",
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("/tmp/test.outgoing.md"),
        extra={},
        content_text="",
    )


class _Repo:
    def __init__(
        self,
        entities: list[EntityRecord],
        connections: list[ConnectionRecord],
        *,
        hidden_connection_ids: set[str] | None = None,
    ) -> None:
        self._entities = {entity.artifact_id: entity for entity in entities}
        self._connections = {conn.artifact_id: conn for conn in connections}
        self._hidden_connection_ids = hidden_connection_ids or set()

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        if artifact_id in self._hidden_connection_ids:
            return None
        return self._connections.get(artifact_id)

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> list[dict[str, str]]:
        entity_set = set(entity_ids)
        return [
            {"artifact_id": conn.artifact_id, "source": conn.source, "target": conn.target}
            for conn in self._connections.values()
            if conn.source in entity_set or conn.target in entity_set
        ]

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: str = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        return [
            conn
            for conn in self._connections.values()
            if (conn_type is None or conn.conn_type == conn_type)
            and (conn.source == entity_id or conn.target == entity_id)
        ]


def test_resolve_diagram_selection_auto_includes_exclusive_junction() -> None:
    process = _entity("PRC@1.a.process-a", "process", "Process A")
    function_a = _entity("FNC@1.a.function-a", "function", "Function A", subdomain="functions")
    function_b = _entity("FNC@1.b.function-b", "function", "Function B", subdomain="functions")
    junction = _entity("JNA@1.a.and-a", "and-junction", "AND A", subdomain="junctions")
    flow_a = _conn(function_a.artifact_id, junction.artifact_id)
    flow_b = _conn(junction.artifact_id, function_b.artifact_id)
    repo = _Repo([process, function_a, function_b, junction], [flow_a, flow_b])

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo,
        [process.artifact_id, function_a.artifact_id, function_b.artifact_id],
        [],
    )

    assert [entity.artifact_id for entity in entities] == [
        process.artifact_id,
        function_a.artifact_id,
        function_b.artifact_id,
        junction.artifact_id,
    ]
    assert {conn.artifact_id for conn in connections} == {flow_a.artifact_id, flow_b.artifact_id}
    assert entity_ids_used == [
        process.artifact_id,
        function_a.artifact_id,
        function_b.artifact_id,
        junction.artifact_id,
    ]
    assert set(connection_ids_used) == {flow_a.artifact_id, flow_b.artifact_id}


def test_resolve_diagram_selection_skips_nonexclusive_junction() -> None:
    function_a = _entity("FNC@1.a.function-a", "function", "Function A", subdomain="functions")
    function_b = _entity("FNC@1.b.function-b", "function", "Function B", subdomain="functions")
    external = _entity("FNC@1.c.function-c", "function", "Function C", subdomain="functions")
    junction = _entity("JNA@1.a.and-a", "and-junction", "AND A", subdomain="junctions")
    flow_a = _conn(function_a.artifact_id, junction.artifact_id)
    flow_b = _conn(junction.artifact_id, function_b.artifact_id)
    flow_c = _conn(junction.artifact_id, external.artifact_id)
    repo = _Repo([function_a, function_b, external, junction], [flow_a, flow_b, flow_c])

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo,
        [function_a.artifact_id, function_b.artifact_id],
        [],
    )

    assert [entity.artifact_id for entity in entities] == [function_a.artifact_id, function_b.artifact_id]
    assert connections == []
    assert entity_ids_used == [function_a.artifact_id, function_b.artifact_id]
    assert connection_ids_used == []


def test_resolve_diagram_selection_drops_unresolvable_connection_ids() -> None:
    function_a = _entity("FNC@1.a.function-a", "function", "Function A", subdomain="functions")
    function_b = _entity("FNC@1.b.function-b", "function", "Function B", subdomain="functions")
    junction = _entity("JNA@1.a.and-a", "and-junction", "AND A", subdomain="junctions")
    flow_a = _conn(function_a.artifact_id, junction.artifact_id)
    flow_b = _conn(junction.artifact_id, function_b.artifact_id)
    repo = _Repo(
        [function_a, function_b, junction],
        [flow_a, flow_b],
        hidden_connection_ids={flow_b.artifact_id},
    )

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo,
        [function_a.artifact_id, function_b.artifact_id],
        [],
    )

    assert [entity.artifact_id for entity in entities] == [
        function_a.artifact_id,
        function_b.artifact_id,
        junction.artifact_id,
    ]
    assert [conn.artifact_id for conn in connections] == [flow_a.artifact_id]
    assert entity_ids_used == [
        function_a.artifact_id,
        function_b.artifact_id,
        junction.artifact_id,
    ]
    assert connection_ids_used == [flow_a.artifact_id]
