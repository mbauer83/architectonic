"""Registry-backed diagram scaffold rendering."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.diagram_type_registry import find_diagram_type, get_diagram_type
from src.infrastructure.mcp.artifact_mcp.context import (
    RepoScope,
    repo_cached,
    resolve_repo_roots,
    roots_key,
)


def build_diagram_scaffold(
    *,
    entity_ids: list[str],
    diagram_name: str,
    direction: Literal["top_to_bottom", "left_to_right"],
    repo_root: str | None,
    repo_scope: RepoScope,
) -> dict[str, object]:
    roots = resolve_repo_roots(
        repo_scope=repo_scope,
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    repo = repo_cached(roots_key(roots))

    entities: list[EntityRecord] = []
    not_found: list[str] = []
    missing_alias: list[str] = []

    for entity_id in entity_ids:
        entity = repo.get_entity(entity_id)
        if entity is None:
            not_found.append(entity_id)
            continue
        if not entity.display_alias:
            missing_alias.append(entity_id)
            continue
        entities.append(entity)

    resolved_ids = {entity.artifact_id for entity in entities}
    connections = _selected_connections(repo=repo, entity_ids=resolved_ids)
    kind_name = _scaffold_diagram_kind_name(entities)
    puml = get_diagram_type(kind_name).renderer.render_body(
        diagram_name,
        entities,
        connections,
        kind_name,
        Path("."),
    )
    puml = _apply_requested_direction(puml, direction)

    return {
        "puml": puml,
        "entities_included": [
            {
                "artifact_id": entity.artifact_id,
                "alias": entity.display_alias,
                "name": entity.name,
                "type": entity.artifact_type,
            }
            for entity in entities
        ],
        "connections_included": [
            {
                "source_alias": _alias_for_entity(entities, conn.source),
                "conn_dir": conn.conn_type.removeprefix("archimate-"),
                "target_alias": _alias_for_entity(entities, conn.target),
            }
            for conn in connections
        ],
        "entities_not_found": not_found,
        "entities_missing_alias": missing_alias,
    }


def _selected_connections(*, repo, entity_ids: set[str]) -> list[ConnectionRecord]:
    connections: list[ConnectionRecord] = []
    seen: set[str] = set()
    for entity_id in entity_ids:
        for conn in repo.find_connections_for(entity_id, direction="outbound"):
            if conn.target not in entity_ids or conn.artifact_id in seen:
                continue
            connections.append(conn)
            seen.add(conn.artifact_id)
    return connections


def _scaffold_diagram_kind_name(entities: list[EntityRecord]) -> str:
    domains = {entity.domain for entity in entities if entity.domain and entity.domain != "common"}
    if len(domains) == 1:
        candidate = f"archimate-{next(iter(domains))}"
        if find_diagram_type(candidate) is not None:
            return candidate
    return "archimate-layered"


def _apply_requested_direction(
    puml: str,
    direction: Literal["top_to_bottom", "left_to_right"],
) -> str:
    if direction == "top_to_bottom":
        return puml
    if "top to bottom direction" in puml:
        return puml.replace("top to bottom direction", "left to right direction", 1)
    match = re.search(r"(@startuml[^\n]*\n(?:!include[^\n]*\n)*)\n", puml)
    if match is None:
        return puml
    insert_at = match.end()
    return f"{puml[:insert_at]}left to right direction\n\n{puml[insert_at:]}"


def _alias_for_entity(entities: list[EntityRecord], artifact_id: str) -> str:
    for entity in entities:
        if entity.artifact_id == artifact_id:
            return entity.display_alias
    return artifact_id
