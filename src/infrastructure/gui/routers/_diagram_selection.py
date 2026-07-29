from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.domain.modules.module_types import ElementClassName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


@lru_cache(maxsize=None)
def _junction_types() -> frozenset[str]:
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return frozenset(get_module_registry().entity_types_with_class(ElementClassName("junction")))


def _unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


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
