"""local-neighborhood/v1 strategy.

Candidate set = all entities and connections reachable by bounded BFS from
``root_entity_ids`` up to ``max_hops`` traversals.

Supported pre_filters:
  - ``direction``: "any" (default) | "outbound" | "inbound"
  - ``connection_types``: list of allowed connection type names
  - ``entity_types``: list of allowed entity type names for reached nodes
"""

from __future__ import annotations

from src.application.derivation.types import CandidateSet, ModelQuery
from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.viewpoints.view_derivations import SourceModelSnapshot

_VALID_DIRECTIONS = frozenset({"any", "outbound", "inbound"})


def derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    """BFS from root_entity_ids up to max_hops, filtered by connection/entity type and direction."""
    raw_roots = params.get("root_entity_ids")
    roots: list[str] = [str(x) for x in raw_roots] if isinstance(raw_roots, list) else []
    if not roots and params.get("root_entity_id") is not None:
        roots = [str(params["root_entity_id"])]

    max_hops_raw = params.get("max_hops", 1)
    max_hops = int(max_hops_raw) if isinstance(max_hops_raw, (int, float)) else 1

    pre = params.get("pre_filters")
    pre_filters: dict[str, object] = pre if isinstance(pre, dict) else {}

    direction_raw = pre_filters.get("direction", "any")
    direction = str(direction_raw) if direction_raw in _VALID_DIRECTIONS else "any"

    allowed_conn_types = _to_str_set(pre_filters.get("connection_types"))
    allowed_entity_types = _to_str_set(pre_filters.get("entity_types"))

    known_entities = query.entity_ids()
    valid_roots = [r for r in roots if r in known_entities]

    entity_ids, connection_ids = _bfs(
        valid_roots, max_hops, direction, allowed_conn_types, allowed_entity_types, query
    )
    return CandidateSet(entity_ids=entity_ids, connection_ids=connection_ids)


def _to_str_set(raw: object) -> set[str] | None:
    return {str(t) for t in raw} if isinstance(raw, list) else None


def _bfs(
    roots: list[str],
    max_hops: int,
    direction: str,
    allowed_conn_types: set[str] | None,
    allowed_entity_types: set[str] | None,
    query: ModelQuery,
) -> tuple[frozenset[str], frozenset[str]]:
    visited_entities: set[str] = set(roots)
    visited_connections: set[str] = set()
    frontier: set[str] = set(roots)

    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier: set[str] = set()
        for entity_id in frontier:
            conns: list[ConnectionRecord] = query.find_connections_for(
                entity_id, direction=direction, conn_type=None  # type: ignore[arg-type]
            )
            for conn in conns:
                if allowed_conn_types is not None and conn.conn_type not in allowed_conn_types:
                    continue
                visited_connections.add(conn.artifact_id)
                other = conn.target if conn.source == entity_id else conn.source
                if other in visited_entities:
                    continue
                if allowed_entity_types is not None:
                    ent = query.get_entity(other)
                    if ent is None or ent.artifact_type not in allowed_entity_types:
                        continue
                visited_entities.add(other)
                next_frontier.add(other)
        frontier = next_frontier

    return frozenset(visited_entities), frozenset(visited_connections)


SPEC = StrategySpec(
    name="local-neighborhood",
    version=1,
    supported_filters=frozenset({"direction", "connection_types", "entity_types"}),
)
