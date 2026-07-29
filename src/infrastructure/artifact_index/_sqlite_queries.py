from __future__ import annotations

import json
import sqlite3

from src.application.artifact_scoring import tokenize

from .types import EntityContextConnection, EntityContextCounts, EntityContextReadModel

# Entity name column (position 1) gets 15× weight over content_text (0.5).
# Columns: artifact_id(UNINDEXED), name, artifact_type, domain, subdomain, keywords, content_text, display_label
_ENT_WEIGHTS = "0, 15.0, 1.0, 1.0, 1.0, 4.0, 0.5, 4.0"


def _entity_exclusion_filter(excluded_entity_types: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    """Prepared NOT IN filter, applied before the per-kind LIMIT so hidden entity
    rows never consume the result budget."""
    if not excluded_entity_types:
        return "", ()
    placeholders = ",".join("?" * len(excluded_entity_types))
    return f" AND artifact_type NOT IN ({placeholders})", tuple(sorted(excluded_entity_types))


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    include_entities: bool = True,
    include_connections: bool = True,
    include_diagrams: bool = True,
    include_documents: bool = True,
    excluded_entity_types: frozenset[str] = frozenset(),
    fts_enabled: bool,
) -> list[tuple[str, str, float]]:
    tokens = tokenize(query.lower())
    if not tokens or not fts_enabled:
        return []
    match_query = " OR ".join(f'"{token}"' for token in tokens)
    per_kind_limit = max(limit, 1)
    entity_filter_sql, entity_filter_params = _entity_exclusion_filter(excluded_entity_types)
    # Per-kind subqueries each get their own ORDER BY + LIMIT so that a dominant
    # kind (e.g. hundreds of entity hits) cannot crowd out minority kinds.
    kind_rows: list[tuple[bool, str, str, str, str, tuple[str, ...]]] = [
        (include_entities, "entity", "entities_fts", f"-bm25(entities_fts, {_ENT_WEIGHTS})",
         entity_filter_sql, entity_filter_params),
        (include_connections, "connection", "connections_fts", "-bm25(connections_fts)", "", ()),
        (include_diagrams, "diagram", "diagrams_fts", "-bm25(diagrams_fts)", "", ()),
        (include_documents, "document", "documents_fts", "-bm25(documents_fts)", "", ()),
    ]
    subqueries: list[str] = []
    params: list[str] = []
    for included, record_type, table, score_expr, filter_sql, filter_params in kind_rows:
        if not included:
            continue
        subqueries.append(
            f"SELECT artifact_id, '{record_type}' AS record_type, {score_expr} AS score "
            f"FROM {table} WHERE {table} MATCH ?{filter_sql} "
            f"ORDER BY score DESC LIMIT {per_kind_limit}"
        )
        params.append(match_query)
        params.extend(filter_params)
    if not subqueries:
        return []
    sql = (
        "SELECT artifact_id, record_type, score FROM ("
        + " UNION ALL ".join(f"SELECT * FROM ({sq})" for sq in subqueries)
        + ") ORDER BY score DESC, artifact_id ASC"
    )
    rows = conn.execute(sql, params).fetchall()
    return [(str(r["artifact_id"]), str(r["record_type"]), float(r["score"])) for r in rows]


def all_connection_stats(conn: sqlite3.Connection) -> dict[str, tuple[int, int, int]]:
    rows = conn.execute("SELECT entity_id, conn_in, conn_sym, conn_out FROM entity_context_stats").fetchall()
    return {str(r["entity_id"]): (int(r["conn_in"]), int(r["conn_sym"]), int(r["conn_out"])) for r in rows}


def connection_stats_for(conn: sqlite3.Connection, entity_id: str) -> tuple[int, int, int]:
    row = conn.execute(
        "SELECT conn_in, conn_sym, conn_out FROM entity_context_stats WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        return (0, 0, 0)
    return (int(row["conn_in"]), int(row["conn_sym"]), int(row["conn_out"]))


def connection_stats_for_set(conn: sqlite3.Connection, entity_ids: frozenset[str]) -> dict[str, tuple[int, int, int]]:
    if not entity_ids:
        return {}
    placeholders = ",".join("?" * len(entity_ids))
    rows = conn.execute(
        (
            "SELECT entity_id, conn_in, conn_sym, conn_out "
            f"FROM entity_context_stats WHERE entity_id IN ({placeholders})"
        ),
        tuple(entity_ids),
    ).fetchall()
    return {str(r["entity_id"]): (int(r["conn_in"]), int(r["conn_sym"]), int(r["conn_out"])) for r in rows}


def connection_ids_by_types(conn: sqlite3.Connection, types: frozenset[str]) -> list[str]:
    if not types:
        return []
    placeholders = ",".join("?" * len(types))
    sql = f"SELECT artifact_id FROM connections WHERE conn_type IN ({placeholders}) ORDER BY artifact_id"
    rows = conn.execute(sql, tuple(types)).fetchall()
    return [str(row["artifact_id"]) for row in rows]


def connection_ids_by_types_for_entity_set(
    conn: sqlite3.Connection,
    types: frozenset[str],
    entity_ids: frozenset[str],
) -> list[str]:
    if not types or not entity_ids:
        return []
    type_placeholders = ",".join("?" * len(types))
    entity_placeholders = ",".join("?" * len(entity_ids))
    sql = (
        "SELECT DISTINCT artifact_id FROM connections "
        f"WHERE conn_type IN ({type_placeholders}) "
        f"AND (source IN ({entity_placeholders}) OR target IN ({entity_placeholders})) "
        "ORDER BY artifact_id"
    )
    params = tuple(types) + tuple(entity_ids) + tuple(entity_ids)
    rows = conn.execute(sql, params).fetchall()
    return [str(row["artifact_id"]) for row in rows]


def connection_ids_for(
    conn: sqlite3.Connection,
    entity_id: str,
    *,
    direction: str = "any",
    conn_type: str | None = None,
) -> list[str]:
    where = ["entity_id = ?"]
    params: list[str] = [entity_id]
    if direction == "outbound":
        # Include directed outbound + symmetric connections where this entity is the source.
        where.append("(direction_bucket = 'outbound' OR (direction_bucket = 'symmetric' AND source_id = ?))")
        params.append(entity_id)
    elif direction == "inbound":
        # Include directed inbound + symmetric connections where this entity is the target.
        where.append("(direction_bucket = 'inbound' OR (direction_bucket = 'symmetric' AND target_id = ?))")
        params.append(entity_id)
    elif direction != "any":
        raise ValueError(f"Unsupported direction: {direction!r}")
    if conn_type is not None:
        where.append("conn_type = ?")
        params.append(conn_type)
    sql = (
        "SELECT DISTINCT connection_id AS artifact_id FROM entity_context_edges WHERE "
        + " AND ".join(where)
        + " ORDER BY artifact_id"
    )
    rows = conn.execute(sql, params).fetchall()
    return [str(row["artifact_id"]) for row in rows]


def connections_for_entity_set(
    conn: sqlite3.Connection,
    entity_ids: frozenset[str],
) -> list[dict]:
    """Single query returning all entity_context_edges rows touching any entity in the set."""
    if not entity_ids:
        return []
    phs = ",".join("?" * len(entity_ids))
    rows = conn.execute(
        f"SELECT * FROM entity_context_edges WHERE entity_id IN ({phs})",
        tuple(entity_ids),
    ).fetchall()
    # Deduplicate by connection_id; prefer outbound perspective when multiple rows exist
    seen: dict[str, dict] = {}
    for row in rows:
        cid = str(row["connection_id"])
        existing = seen.get(cid)
        if existing is None or str(row["direction_bucket"]) == "outbound":
            seen[cid] = dict(row)
    return list(seen.values())


def find_neighbors(
    conn: sqlite3.Connection,
    entity_id: str,
    *,
    max_hops: int,
    conn_type: str | None,
) -> dict[str, set[str]]:
    if max_hops < 1:
        return {}
    rows = conn.execute(
        """
        WITH RECURSIVE walk(depth, entity_id, visited) AS (
            SELECT 0, ?, ',' || ? || ','
            UNION ALL
            SELECT
                walk.depth + 1,
                CASE WHEN connections.source = walk.entity_id
                     THEN connections.target ELSE connections.source END,
                walk.visited
                    || CASE WHEN connections.source = walk.entity_id
                            THEN connections.target ELSE connections.source END
                    || ','
            FROM walk
            JOIN connections ON (
                connections.source = walk.entity_id
                OR connections.target = walk.entity_id
            )
            WHERE walk.depth < ?
              AND (? IS NULL OR connections.conn_type = ?)
              AND instr(walk.visited,
                  ',' || CASE WHEN connections.source = walk.entity_id
                              THEN connections.target ELSE connections.source END
                  || ',') = 0
        )
        SELECT depth, entity_id FROM walk WHERE depth > 0
        """,
        (entity_id, entity_id, max_hops, conn_type, conn_type),
    ).fetchall()
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(str(int(row["depth"])), set()).add(str(row["entity_id"]))
    return result


def diagrams_referencing_type(
    conn: sqlite3.Connection, type_id: str
) -> list[tuple[str, str, str]]:
    """Return (diagram_id, classifier_local_id, attr_name) tuples for a given type_id."""
    rows = conn.execute(
        "SELECT diagram_id, classifier_local_id, attr_name FROM attribute_type_refs WHERE type_id=?",
        (type_id,),
    ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def entity_context(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_data: dict[str, object],
    generation: int,
    etag: str,
) -> EntityContextReadModel | None:
    counts_row = conn.execute(
        "SELECT conn_in, conn_out, conn_sym FROM entity_context_stats WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    counts: EntityContextCounts = {
        "conn_in": int(counts_row["conn_in"]) if counts_row is not None else 0,
        "conn_out": int(counts_row["conn_out"]) if counts_row is not None else 0,
        "conn_sym": int(counts_row["conn_sym"]) if counts_row is not None else 0,
    }
    grouped: dict[str, list[EntityContextConnection]] = {
        "outbound": [],
        "inbound": [],
        "symmetric": [],
    }
    rows = conn.execute(
        """
        SELECT *
        FROM entity_context_edges
        WHERE entity_id = ?
        ORDER BY direction_bucket, connection_id
        """,
        (entity_id,),
    ).fetchall()
    for row in rows:
        grouped[str(row["direction_bucket"])].append(
            {
                "artifact_id": str(row["connection_id"]),
                "source": str(row["source_id"]),
                "target": str(row["target_id"]),
                "conn_type": str(row["conn_type"]),
                "version": str(row["connection_version"]),
                "status": str(row["connection_status"]),
                "path": str(row["path"]),
                "content_text": str(row["content_text"]),
                "associated_entities": json.loads(str(row["associated_entities_json"])),
                "src_multiplicity": str(row["src_multiplicity"]),
                "tgt_multiplicity": str(row["tgt_multiplicity"]),
                "specialization": str(row["specialization"]),
                "source_name": str(row["source_name"]),
                "target_name": str(row["target_name"]),
                "source_artifact_type": str(row["source_artifact_type"]),
                "target_artifact_type": str(row["target_artifact_type"]),
                "source_domain": str(row["source_domain"]),
                "target_domain": str(row["target_domain"]),
                "source_scope": str(row["source_scope"]),
                "target_scope": str(row["target_scope"]),
                "other_entity_id": str(row["other_entity_id"]),
                "direction": str(row["direction_bucket"]),
            }
        )
    return {
        "entity": entity_data,
        "connections": grouped,
        "counts": counts,
        "generation": generation,
        "etag": etag,
    }
