"""What a diagram holds that a per-instance or per-relation statement may name, read from its frontmatter.

A layout, and an edge label, are keyed by the identities the diagram already uses: the instances it
draws, the groupings it states, the relations it draws. This is the one place those are collected
from a diagram's own statements, so the write path that prunes a layout, the file writer that
refuses to store geometry for nothing, and the verifier that reports it agree on what "on the
diagram" means.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.application.diagram_occurrences import occurrence_statements
from src.domain.artifact_id import MalformedArtifactIdError, canonical_entity_key, connection_id_as_written
from src.domain.diagrams.authored_groupings import RuleKey, grouping_ids
from src.domain.diagrams.drawn_relations import held_connection_id, relations_drawn_for
from src.domain.diagrams.layout.layout_checks import DiagramIdentities


def _rows(value: object) -> list[Mapping[str, object]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def drawn_instances(entity_ids_used: Sequence[str] | None, diagram_entities: object) -> frozenset[str]:
    """Every instance a diagram draws: its entities' base instances and each further occurrence."""
    stated = diagram_entities if isinstance(diagram_entities, Mapping) else None
    return frozenset(
        [canonical_entity_key(str(entity_id)) for entity_id in entity_ids_used or ()]
        + [occurrence_id for occurrence_id, _backing in occurrence_statements(stated)]
    )


def drawn_relation_ends(
    connection_ids_used: Sequence[str] | None, diagram_entities: object, diagram_connections: object
) -> dict[str, tuple[str, str]]:
    """Every relation a diagram draws, by key text, with the instances at its ends.

    A model connection contributes one relation per drawing the overlay names; a connection the
    diagram holds itself is keyed by its id within the diagram and has no instances to speak of.
    """
    stated = diagram_entities if isinstance(diagram_entities, Mapping) else None
    occurrences = {occurrence_id for occurrence_id, _backing in occurrence_statements(stated)}
    overlay = _rows(diagram_connections)
    relations: dict[str, tuple[str, str]] = {}
    for connection_id in connection_ids_used or ():
        try:
            source, target, _conn_type = connection_id_as_written(str(connection_id))
        except MalformedArtifactIdError:
            continue
        for drawn in relations_drawn_for(
            str(connection_id), source=source, target=target, diagram_connections=overlay, occurrences=occurrences
        ):
            relations[drawn.key.text] = (
                canonical_entity_key(drawn.source_instance), canonical_entity_key(drawn.target_instance),
            )
    for row in overlay:
        if (held := held_connection_id(row)) is not None:
            relations.setdefault(held, (str(row.get("source") or ""), str(row.get("target") or "")))
    return relations


def diagram_identities(
    *,
    entity_ids_used: Sequence[str] | None,
    connection_ids_used: Sequence[str] | None,
    diagram_entities: object,
    diagram_connections: object,
    authored_groupings: object,
    rule_admits: Callable[[RuleKey], bool] = lambda _key: True,
) -> DiagramIdentities:
    """The identities of a diagram stating these things. *rule_admits* defaults to not judging rules."""
    return DiagramIdentities(
        instances=drawn_instances(entity_ids_used, diagram_entities),
        grouping_ids=frozenset(grouping_ids(authored_groupings)),
        relations=drawn_relation_ends(connection_ids_used, diagram_entities, diagram_connections),
        rule_admits=rule_admits,
    )
