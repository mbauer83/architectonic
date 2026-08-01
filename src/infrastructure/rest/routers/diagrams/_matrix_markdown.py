"""Matrix-table markdown assembly for the matrix GUI write endpoints — kept out of the router
module so the endpoint file stays focused on request handling."""

from __future__ import annotations

from typing import Any


def build_matrix_markdown(
    entity_ids: list[str],
    conn_type_configs: list[dict[str, object]],
    combined: bool,
    repo: Any,
    from_entity_ids: list[str] | None = None,
    to_entity_ids: list[str] | None = None,
) -> str:
    from src.application.modeling.matrix_builder import ConnTypeConfig, build_matrix_tables
    from src.infrastructure.app_bootstrap import process_runtime_catalogs

    all_ids = list(set(from_entity_ids or entity_ids) | set(to_entity_ids or entity_ids))
    entity_names: dict[str, str] = {}
    for eid in all_ids:
        rec = repo.get_entity(eid)
        entity_names[eid] = rec.name if rec else eid

    connections = repo.candidate_connections_for_entities(all_ids)
    configs = [
        ConnTypeConfig(conn_type=str(c["conn_type"]), active=bool(c.get("active", True))) for c in conn_type_configs
    ]
    abbrevs = process_runtime_catalogs().ontology.matrix_connection_type_abbreviations()
    return build_matrix_tables(
        entity_ids=entity_ids,
        conn_type_configs=configs,
        combined=combined,
        entity_names=entity_names,
        connections=connections,
        from_entity_ids=from_entity_ids,
        to_entity_ids=to_entity_ids,
        matrix_abbreviations=abbrevs,
    )
