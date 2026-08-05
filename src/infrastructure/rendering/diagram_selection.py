"""Which artifacts a diagram draws, given the ones its author named.

A selection is not simply the list handed in. A junction stands for a relationship rather than an
element, so a diagram that names every participant of one but not the junction itself would draw the
participants unconnected; the junction and its legs are pulled in, transitively, and only when *all*
of its other endpoints are already selected — a junction reaching outside the picture would draw a leg
to nothing.

It lived under ``rest/routers/diagrams/`` and had nothing to do with HTTP: the write path, the MCP
tools and two other routers all needed it, and a write op reaching into a REST router for it would be
the wrong dependency in the wrong direction. It sits beside the renderer it feeds, and asks it which
types are junctions rather than looking that up a second way.
"""

from __future__ import annotations

from typing import Any

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.diagram_builder import junction_type_names as _junction_types


def _unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def connections_among(repo: Any, entity_ids: list[str]) -> list[str]:
    """The model connections whose *both* endpoints are in *entity_ids*.

    What a diagram of a set of entities draws without being told: a connection with one endpoint
    outside the selection has nothing to attach to.
    """
    selected = set(entity_ids)
    return [
        str(conn["artifact_id"])
        for conn in repo.candidate_connections_for_entities(entity_ids)
        if str(conn["source"]) in selected and str(conn["target"]) in selected
    ]


def resolve_diagram_selection(
    repo: Any,
    entity_ids: list[str],
    connection_ids: list[str],
) -> tuple[list[EntityRecord], list[ConnectionRecord], list[str], list[str]]:
    expanded_entity_ids = _unique_ids(entity_ids)
    expanded_connection_ids = _unique_ids(connection_ids)
    entity_set = set(expanded_entity_ids)
    connection_set = set(expanded_connection_ids)

    while True:
        candidate_junction_ids: set[str] = set()
        for conn in repo.candidate_connections_for_entities(list(entity_set)):
            source_id = str(conn["source"])
            target_id = str(conn["target"])
            if source_id not in entity_set:
                source_rec = repo.get_entity(source_id)
                if source_rec is not None and source_rec.artifact_type in _junction_types():
                    candidate_junction_ids.add(source_id)
            if target_id not in entity_set:
                target_rec = repo.get_entity(target_id)
                if target_rec is not None and target_rec.artifact_type in _junction_types():
                    candidate_junction_ids.add(target_id)

        added_entity = False
        for junction_id in sorted(candidate_junction_ids):
            junction_rec = repo.get_entity(junction_id)
            if junction_rec is None or junction_rec.artifact_type not in _junction_types():
                continue
            junction_connections = repo.find_connections_for(junction_id, direction="any")
            if not junction_connections:
                continue
            other_ids = {
                endpoint
                for conn in junction_connections
                for endpoint in (conn.source, conn.target)
                if endpoint != junction_id
            }
            if any(other_id not in entity_set for other_id in other_ids):
                continue
            if junction_id not in entity_set:
                entity_set.add(junction_id)
                expanded_entity_ids.append(junction_id)
                added_entity = True
            for conn in junction_connections:
                if conn.artifact_id not in connection_set:
                    connection_set.add(conn.artifact_id)
                    expanded_connection_ids.append(conn.artifact_id)
        if not added_entity:
            break

    entities = [entity for eid in expanded_entity_ids if (entity := repo.get_entity(eid)) is not None]
    connections = [conn for cid in expanded_connection_ids if (conn := repo.get_connection(cid)) is not None]
    return (
        entities,
        connections,
        [entity.artifact_id for entity in entities],
        [conn.artifact_id for conn in connections],
    )
