"""incident-connections/v1 strategy.

Candidate set = all connections incident to the given entity_ids (non-recursive
edge incidence, not BFS traversal), plus the endpoint entities of those connections.

Supported pre_filters:
  - ``direction``: "any" (default) | "outbound" | "inbound"
  - ``connection_types``: list of allowed connection type names
"""

from __future__ import annotations

from src.application.derivation.types import CandidateSet, ModelQuery
from src.domain.artifact_id import stable_id
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.viewpoints.view_derivations import SourceModelSnapshot

_VALID_DIRECTIONS = frozenset({"any", "outbound", "inbound"})


def derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    """Find connections incident to entity_ids; add their endpoint entities to candidates."""
    raw_entity_ids = params.get("entity_ids")
    entity_ids: list[str] = (
        [str(x) for x in raw_entity_ids] if isinstance(raw_entity_ids, list) else []
    )

    pre = params.get("pre_filters")
    pre_filters: dict[str, object] = pre if isinstance(pre, dict) else {}

    direction_raw = pre_filters.get("direction", "any")
    direction = str(direction_raw) if direction_raw in _VALID_DIRECTIONS else "any"

    raw_types = pre_filters.get("connection_types")
    allowed_conn_types: set[str] | None = (
        {str(t) for t in raw_types} if isinstance(raw_types, list) else None
    )

    known_short_entities = {stable_id(e) for e in query.entity_ids()}
    valid_entity_ids = [eid for eid in entity_ids if stable_id(eid) in known_short_entities]

    found_connection_ids: set[str] = set()
    endpoint_entity_ids: set[str] = set(valid_entity_ids)

    for eid in valid_entity_ids:
        for conn in query.find_connections_for(eid, direction=direction, conn_type=None):  # type: ignore[arg-type]
            if allowed_conn_types is not None and conn.conn_type not in allowed_conn_types:
                continue
            found_connection_ids.add(conn.artifact_id)
            endpoint_entity_ids.add(conn.source)
            endpoint_entity_ids.add(conn.target)

    return CandidateSet(
        entity_ids=frozenset(endpoint_entity_ids),
        connection_ids=frozenset(found_connection_ids),
    )


SPEC = StrategySpec(
    name="incident-connections",
    version=1,
    supported_filters=frozenset({"direction", "connection_types"}),
)
