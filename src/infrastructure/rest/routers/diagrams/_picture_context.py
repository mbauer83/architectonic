"""What an editor reads about a picture beside the diagram it draws: its elements and relations, what the model
relates them to, and what lies one and two steps away.

One reading for every picture an editor opens on: a stored diagram's (`diagram_context_payload`), and a
candidate's, which starts from a stored diagram or from a view generated from what the candidate reads over.
*reach* widens what the relations and the neighbourhood are read around beyond what the picture draws: a
candidate reads over elements its starting picture may not draw yet.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.application._diagram_entity_extraction import (
    HELD_CONNECTION_MARK,
    extract_diagram_connections,
    extract_diagram_entities,
)
from src.application.artifacts.parsing import normalize_puml_alias
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import stable_conn_id
from src.domain.diagrams.relation_key import labels_by_relation
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.rendering.archimate_occurrences import drawn_labels_by_instance
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams._context import (
    _held_record_scope,
    candidate_connections_for_entities,
    drawn_entities,
    hop_suggestions,
    parse_explicit_connection_pairs,
)
from src.infrastructure.rest.routers.diagrams._derived_entities import derived_entity_rows


def picture_context_payload(
    repo: Any, record: DiagramRecord, puml: str, catalogs: RuntimeCatalogs, *,
    read_entities: Mapping[str, Any], reach: Iterable[str] = (),
) -> dict[str, Any]:
    """Everything the context read answers about the picture *puml* of *record*, but the diagram itself.

    *read_entities* are the diagram-entities as the diagram read serves them, which the type's projection reads.
    """
    version = repo.read_model_version()
    entities = drawn_entities(repo, record, puml, catalogs)
    entity_ids = [str(entity["artifact_id"]) for entity in entities]
    scope = _held_record_scope(catalogs, record.diagram_type)
    extracted = {rec.artifact_id: rec for rec in extract_diagram_entities(record, scope)}
    in_picture = {
        entity_id: rec for entity_id in entity_ids
        if (rec := repo.get_entity(entity_id) or extracted.get(entity_id)) is not None
    }
    explicit_pairs = parse_explicit_connection_pairs(puml)
    raw_entities = record.extra.get("diagram-entities") if record.extra else None
    diagram_entities: dict[str, Any] = raw_entities if isinstance(raw_entities, dict) else {}
    dt = catalogs.diagram_types.find_diagram_type(record.diagram_type)
    type_extras = dt.build_context_extras(repo, record.artifact_id, diagram_entities) if dt else {}
    # What the type's projection draws and as what, from the diagram-entities the read serves: the
    # same rows the preview answers, so an editor is right before its first preview.
    root = s.maybe_engagement_root()
    derived = (
        derived_entity_rows(dt, record.diagram_type, dict(read_entities), root)
        if dt is not None and root is not None else None
    )
    reached = list(dict.fromkeys([*entity_ids, *reach]))
    return {
        "entities": entities,
        "connections": _drawn_connections(repo, record, in_picture, explicit_pairs, scope),
        # What each instance is called in the body as it stands, by instance id. Read off the body
        # rather than derived, because a hand-laid body may call an element something its record
        # does not — and an editor that cannot see that would revert it on the first save.
        "drawn_labels": drawn_labels_by_instance(puml, diagram_entities, in_picture),
        "candidate_connections": candidate_connections_for_entities(repo, reached),
        "suggested_entities": hop_suggestions(repo, reached, catalogs, max_hops=2, limit_per_hop=25),
        "explicit_connection_pairs": [list(pair) for pair in sorted(explicit_pairs)],
        "generation": version.generation,
        "etag": version.etag,
        # Namespaced, not merged: the envelope declares its own fields, and a hook free to add a key
        # beside them would make the whole response a contract promising nothing.
        "type_extras": type_extras or None,
        "derived_entities": derived,
    }


def _drawn_connections(
    repo: Any, record: DiagramRecord, in_picture: Mapping[str, Any], explicit_pairs: set[tuple[str, str]],
    scope: Any,
) -> list[dict[str, Any]]:
    """Each relation the picture draws between two of its elements, as the editor lists it."""
    edge_labels = labels_by_relation(record.extra.get("edge-labels") if record.extra else None)
    connection_records = {conn.artifact_id: conn for conn in repo.list_connections()}
    connection_records.update({conn.artifact_id: conn for conn in extract_diagram_connections(record, scope)})
    connections: list[dict[str, Any]] = []
    for conn in connection_records.values():
        src, tgt = in_picture.get(conn.source), in_picture.get(conn.target)
        if src is None or tgt is None:
            continue
        sa = normalize_puml_alias(src.display_alias or "")
        ta = normalize_puml_alias(tgt.display_alias or "")
        is_owned = conn.path == record.path and HELD_CONNECTION_MARK in conn.artifact_id
        if not is_owned and (sa, ta) not in explicit_pairs and (ta, sa) not in explicit_pairs:
            continue
        # The key a statement about this drawn relation is filed under: a connection the diagram
        # holds by its id within the diagram, a model connection by its own.
        edge_key = conn.artifact_id.partition(HELD_CONNECTION_MARK)[2] if is_owned else stable_conn_id(conn.artifact_id)
        d = s.connection_to_dict(conn)
        d.update(source_name=src.name, target_name=tgt.name, source_alias=sa, target_alias=ta, edge_key=edge_key,
                 edge_label_override=edge_labels.get(edge_key))
        connections.append(d)
    return connections
