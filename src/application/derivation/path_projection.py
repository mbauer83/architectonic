"""path-projection/v1 strategy.

Candidate set = ordered connection paths between source and target entities,
filtered by connection type/class and direction, selected per path_policy.

Path key format: ``id1@fwd|id2@rev|...``
  - @fwd: traversed in model edge direction (reversed=false)
  - @rev: traversed against model edge direction (reversed=true)

Supported pre_filters: connection_types, connection_classes, direction,
max_path_length, repo_scope.

path_policy values:
  shortest      (default) — minimum-hop path per (source, target) pair
  all-simple    — every simple (no repeated entity) path up to max_path_length
  class-priority — (stub) falls back to shortest; class scoring requires ontology data
"""

from __future__ import annotations

from collections import deque

from src.application.derivation.types import CandidateSet, ModelQuery
from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.viewpoints.view_derivations import SourceModelSnapshot

_VALID_DIRECTIONS = frozenset({"any", "outbound", "inbound"})
_SUPPORTED_FILTERS = frozenset({
    "connection_types", "connection_classes", "direction", "max_path_length", "repo_scope"
})


def _path_key(steps: list[tuple[str, bool]]) -> str:
    """Canonical path key: 'id1@fwd|id2@rev|...'."""
    return "|".join(f"{cid}@{'rev' if rev else 'fwd'}" for cid, rev in steps)


def _step_endpoints(conn: ConnectionRecord, reversed_flag: bool) -> tuple[str, str]:
    """Return (from_entity, to_entity) honouring the reversed flag."""
    return (conn.target, conn.source) if reversed_flag else (conn.source, conn.target)


def _get_neighbours(
    entity_id: str,
    direction: str,
    allowed_conn_types: set[str] | None,
    query: ModelQuery,
) -> list[tuple[ConnectionRecord, bool]]:
    """Return (connection, reversed) pairs reachable from entity_id."""
    results: list[tuple[ConnectionRecord, bool]] = []
    if direction in ("any", "outbound"):
        for conn in query.find_connections_for(entity_id, direction="outbound"):
            if allowed_conn_types is None or conn.conn_type in allowed_conn_types:
                results.append((conn, False))
    if direction in ("any", "inbound"):
        for conn in query.find_connections_for(entity_id, direction="inbound"):
            if allowed_conn_types is None or conn.conn_type in allowed_conn_types:
                results.append((conn, True))
    return results


def _bfs_shortest(
    source: str,
    targets: set[str],
    max_hops: int,
    direction: str,
    allowed_conn_types: set[str] | None,
    query: ModelQuery,
) -> list[list[tuple[str, bool]]]:
    """BFS to find the shortest path from source to each target entity."""
    found: list[list[tuple[str, bool]]] = []
    visited: set[str] = {source}
    # queue: (current_entity, path_so_far as list of (conn_id, reversed))
    queue: deque[tuple[str, list[tuple[str, bool]]]] = deque([(source, [])])

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for conn, rev in _get_neighbours(current, direction, allowed_conn_types, query):
            _from, to_entity = _step_endpoints(conn, rev)
            if to_entity in visited:
                continue
            new_path = [*path, (conn.artifact_id, rev)]
            if to_entity in targets:
                found.append(new_path)
            visited.add(to_entity)
            queue.append((to_entity, new_path))

    return found


def _dfs_all_simple(
    source: str,
    targets: set[str],
    max_hops: int,
    direction: str,
    allowed_conn_types: set[str] | None,
    query: ModelQuery,
) -> list[list[tuple[str, bool]]]:
    """DFS to enumerate all simple paths from source to each target."""
    found: list[list[tuple[str, bool]]] = []
    visited_entities: set[str] = {source}

    def dfs(current: str, path: list[tuple[str, bool]]) -> None:
        if len(path) >= max_hops:
            return
        neighbours = _get_neighbours(current, direction, allowed_conn_types, query)
        # Sort for deterministic order: by (conn_id, reversed)
        neighbours.sort(key=lambda x: (x[0].artifact_id, x[1]))
        for conn, rev in neighbours:
            _from, to_entity = _step_endpoints(conn, rev)
            if to_entity in visited_entities:
                continue
            new_path = [*path, (conn.artifact_id, rev)]
            if to_entity in targets:
                found.append(new_path)
            visited_entities.add(to_entity)
            dfs(to_entity, new_path)
            visited_entities.discard(to_entity)

    dfs(source, [])
    return found


def derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    """path-projection/v1: enumerate connection paths between source and target entities."""
    raw_sources = params.get("source_entity_ids")
    source_ids: list[str] = [str(x) for x in raw_sources] if isinstance(raw_sources, list) else []
    if not source_ids and params.get("source_entity_id") is not None:
        source_ids = [str(params["source_entity_id"])]

    raw_targets = params.get("target_entity_ids")
    target_ids: set[str] | None = (
        {str(x) for x in raw_targets} if isinstance(raw_targets, list) else None
    )

    max_hops_raw = params.get("max_path_length", 3)
    max_hops = int(max_hops_raw) if isinstance(max_hops_raw, (int, float)) else 3

    pre = params.get("pre_filters")
    pre_filters: dict[str, object] = pre if isinstance(pre, dict) else {}

    direction_raw = pre_filters.get("direction", "outbound")
    direction = str(direction_raw) if direction_raw in _VALID_DIRECTIONS else "outbound"

    allowed_conn_types_raw = pre_filters.get("connection_types")
    allowed_conn_types: set[str] | None = (
        {str(t) for t in allowed_conn_types_raw} if isinstance(allowed_conn_types_raw, list) else None
    )

    path_policy_raw = params.get("path_policy", "shortest")
    path_policy = str(path_policy_raw) if path_policy_raw else "shortest"

    known = query.entity_ids()
    valid_sources = [s for s in source_ids if s in known]

    # All known entities minus sources are candidate targets if none specified
    effective_targets: set[str] = (
        target_ids - set(valid_sources) if target_ids is not None
        else known - set(valid_sources)
    )

    all_path_steps: list[list[tuple[str, bool]]] = []
    for source in valid_sources:
        if path_policy == "all-simple":
            paths = _dfs_all_simple(source, effective_targets, max_hops, direction, allowed_conn_types, query)
        else:
            # shortest and class-priority (class-priority stub: use shortest)
            paths = _bfs_shortest(source, effective_targets, max_hops, direction, allowed_conn_types, query)
        all_path_steps.extend(paths)

    # Deterministic tie-break: sort paths by their canonical key (lexicographic)
    all_path_steps.sort(key=lambda p: _path_key(p))

    path_keys: frozenset[str] = frozenset(_path_key(p) for p in all_path_steps)
    connection_ids: frozenset[str] = frozenset(
        conn_id for path in all_path_steps for conn_id, _ in path
    )

    return CandidateSet(connection_ids=connection_ids, paths=path_keys)


SPEC = StrategySpec(
    name="path-projection",
    version=1,
    supported_filters=_SUPPORTED_FILTERS,
)
