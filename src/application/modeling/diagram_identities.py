"""What a diagram holds that a per-instance or per-relation statement may name, read from its frontmatter.

A layout, and an edge label, are keyed by the identities the diagram already uses: the instances it
draws, the groupings it states, the relations it draws. This is the one place those are collected
from a diagram's own statements, so the write path that prunes a layout, the file writer that
refuses to store geometry for nothing, and the verifier that reports it agree on what "on the
diagram" means.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.application.artifacts.parsing import normalize_puml_alias, standard_alias_of
from src.application.diagram_occurrences import occurrence_alias, occurrence_statements
from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.domain.artifact_id import (
    MalformedArtifactIdError,
    canonical_entity_key,
    connection_id_as_written,
    is_entity_id,
    stable_id,
)
from src.domain.diagrams.authored_groupings import RuleKey, grouping_ids
from src.domain.diagrams.drawn_relations import held_connection_id, relations_drawn_for
from src.domain.diagrams.layout.layout_checks import DiagramIdentities


def _rows(value: object) -> list[Mapping[str, object]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def strings_of(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def alias_by_instance(frontmatter: Mapping[str, object]) -> dict[str, str]:
    """The alias each instance is drawn under, as far as the diagram's own statements say.

    Resolved the way the product assigns one — from the element's id, a further occurrence numbered
    in the order stated, a held element by the alias its row states — and never from another file,
    so the answer cannot depend on what else a checkout happens to hold. An instance whose alias
    cannot be told this way is absent, and a caller treats absence as not knowing.
    """
    aliases: dict[str, str] = {}
    for entity_id in strings_of(frontmatter.get("entity-ids-used")):
        if alias := standard_alias_of(entity_id):
            aliases[stable_id(entity_id)] = normalize_puml_alias(alias)
    stated = frontmatter.get("diagram-entities")
    drawings: dict[str, int] = {}
    for occurrence_id, backing in occurrences_stated(stated, frontmatter.get("bindings")):
        drawings[backing] = drawings.get(backing, 1) + 1
        if base := standard_alias_of(backing):
            aliases[occurrence_id] = occurrence_alias(normalize_puml_alias(base), drawings[backing])
    for rows in (stated.values() if isinstance(stated, Mapping) else ()):
        for row in rows if isinstance(rows, list) else ():
            if isinstance(row, Mapping) and row.get("id") and row.get("alias"):
                aliases[str(row["id"])] = normalize_puml_alias(str(row["alias"]))
    return aliases


def entity_by_alias(frontmatter: Mapping[str, object]) -> dict[str, str]:
    """The model element each alias stands for, in stable form — `alias_by_instance` read backwards.

    An occurrence's alias stands for the element it draws again. An instance that is no model element
    (a held record's local id, an id-shaped string naming nothing) stands for none and is left out.
    """
    backing = dict(occurrences_stated(frontmatter.get("diagram-entities"), frontmatter.get("bindings")))
    return {
        alias: stable_id(element)
        for instance, alias in alias_by_instance(frontmatter).items()
        if is_entity_id(element := backing.get(instance, instance))
    }


def occurrences_stated(diagram_entities: object, bindings: object) -> list[tuple[str, str]]:
    """Every further occurrence a diagram states, as ``(occurrence id, backing entity id)``.

    Read from the diagram as it is *stored*: the entity an occurrence draws again is kept in the
    ``bindings`` block, not on the occurrence, so asking the occurrence alone answers "none" for
    every stored diagram. An in-flight write still carrying the shorthand is read as it stands.
    """
    stated = dict(diagram_entities) if isinstance(diagram_entities, Mapping) else None
    return occurrence_statements(restore_diagram_shorthand(stated, bindings))


def drawn_instances(
    entity_ids_used: Sequence[str] | None, diagram_entities: object, bindings: object = None
) -> frozenset[str]:
    """Every instance a diagram draws: its entities' base instances and each further occurrence."""
    return frozenset(
        [canonical_entity_key(str(entity_id)) for entity_id in entity_ids_used or ()]
        + [occurrence_id for occurrence_id, _backing in occurrences_stated(diagram_entities, bindings)]
    )


def drawn_relation_ends(
    connection_ids_used: Sequence[str] | None,
    diagram_entities: object,
    diagram_connections: object,
    bindings: object = None,
) -> dict[str, tuple[str, str]]:
    """Every relation a diagram draws, by key text, with the instances at its ends.

    A model connection contributes one relation per drawing the overlay names; a connection the
    diagram holds itself is keyed by its id within the diagram and has no instances to speak of.
    """
    occurrences = {occurrence_id for occurrence_id, _backing in occurrences_stated(diagram_entities, bindings)}
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
    bindings: object = None,
    rule_admits: Callable[[RuleKey], bool] = lambda _key: True,
) -> DiagramIdentities:
    """The identities of a diagram stating these things. *rule_admits* defaults to not judging rules."""
    return DiagramIdentities(
        instances=drawn_instances(entity_ids_used, diagram_entities, bindings),
        grouping_ids=frozenset(grouping_ids(authored_groupings)),
        relations=drawn_relation_ends(connection_ids_used, diagram_entities, diagram_connections, bindings),
        rule_admits=rule_admits,
    )
