"""What an ArchiMate diagram says about its *instances*, beyond which entities it holds.

Two keys of ``diagram-entities`` are read here and nowhere else in the renderer: ``occurrence``,
the extran instances of an entity, and ``display_labels``, how an instance is labelled on this diagram.
An instance is named by its **instance id** — the entity's artifact id for its base instance, the
occurrence id for any further one — which is the same identity the GUI's rows and an authored
grouping's members use, so every per-instance statement is keyed the one way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from src.application.artifacts.parsing import normalize_puml_alias
from src.application.puml_alias_declarations import (
    alias_declared_on,
    label_declared_on,
    relabelled_declaration,
)
from src.domain.ontology_representation.artifact_types import EntityRecord

#: The ``diagram-entities`` key holding per-instance labels: ``{instance id: label}``.
DISPLAY_LABELS_KEY = "display_labels"


def occurrence_entities(
    diagram_entities: Mapping[str, object] | None,
    entity_by_id: Mapping[str, EntityRecord],
) -> list[EntityRecord]:
    """Return additional rendered occurrences declared in diagram-entities."""
    if not diagram_entities:
        return []

    counts: dict[str, int] = {}
    result: list[EntityRecord] = []
    for items in diagram_entities.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            backing_id = str(item.get("backing_entity_id") or "").strip()
            occurrence_id = str(item.get("id") or "").strip()
            if not backing_id or not occurrence_id:
                continue
            backing = entity_by_id.get(backing_id)
            if backing is None or not backing.display_alias:
                continue
            base_alias = normalize_puml_alias(backing.display_alias)
            if not base_alias:
                continue
            counts[backing_id] = counts.get(backing_id, 1) + 1
            result.append(
                replace(
                    backing,
                    display_alias=f"{base_alias}__{counts[backing_id]}",
                    host_diagram_id=occurrence_id,
                )
            )
    return result


def display_label_overrides(diagram_entities: Mapping[str, object] | None) -> dict[str, str]:
    """The labels this diagram gives its instances, by instance id.

    A label is what an ArchiMate element is called *on this picture*: the model's name stays what
    it is, so a long name can read short where the box is small without renaming the element
    everywhere it appears. Anything that is not a non-empty string labelling a string key is
    ignored — a malformed entry must not take the whole diagram down.
    """
    if not diagram_entities:
        return {}
    raw = diagram_entities.get(DISPLAY_LABELS_KEY)
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(instance_id): label.strip()
        for instance_id, label in raw.items()
        if isinstance(instance_id, str) and isinstance(label, str) and label.strip()
    }


def instance_labels_by_alias(
    diagram_entities: Mapping[str, object] | None,
    entities: Sequence[EntityRecord],
    occurrences: Sequence[EntityRecord],
) -> dict[str, str]:
    """The labels this diagram gives its instances, by the alias each instance is declared under.

    A base instance is addressed by the entity's artifact id; an occurrence by its occurrence id,
    which `occurrence_entities` carries in ``host_diagram_id``. Declarations know only aliases, so
    the join is made once here for the renderer and for a body that is relabelled in place.
    """
    overrides = display_label_overrides(diagram_entities)
    if not overrides:
        return {}
    by_alias: dict[str, str] = {}
    for entity in entities:
        label = overrides.get(entity.artifact_id)
        if label and entity.display_alias:
            by_alias[normalize_puml_alias(entity.display_alias)] = label
    for occurrence in occurrences:
        label = overrides.get(occurrence.host_diagram_id or "")
        if label and occurrence.display_alias:
            by_alias[normalize_puml_alias(occurrence.display_alias)] = label
    return by_alias


def _alias_by_instance(
    diagram_entities: Mapping[str, object] | None, entity_by_id: Mapping[str, EntityRecord]
) -> dict[str, str]:
    """Every instance this diagram holds, instance id → alias — base instances and occurrences alike."""
    by_instance = {
        entity.artifact_id: normalize_puml_alias(entity.display_alias)
        for entity in entity_by_id.values()
        if entity.display_alias
    }
    for occurrence in occurrence_entities(diagram_entities, entity_by_id):
        if occurrence.host_diagram_id:
            by_instance[occurrence.host_diagram_id] = normalize_puml_alias(occurrence.display_alias)
    return by_instance


def relabel_instances_in_body(
    body: str,
    diagram_entities: Mapping[str, object] | None,
    entity_by_id: Mapping[str, EntityRecord],
) -> str:
    """*body* with every instance ``display_labels`` names called what it says, and nothing else changed.

    For a body that is kept verbatim — a hand-laid diagram, or one a caller supplied — this is how a
    label stated in the frontmatter reaches the picture at all; a rendered body honours the same
    statement through `instance_labels_by_alias`. An instance the statement names but the body does not
    declare is left alone: there is no line to relabel and nothing is invented.
    """
    occurrences = occurrence_entities(diagram_entities, entity_by_id)
    label_by_alias = instance_labels_by_alias(diagram_entities, list(entity_by_id.values()), occurrences)
    if not label_by_alias:
        return body
    lines = body.split("\n")
    relabelled = []
    for line in lines:
        declaration = alias_declared_on(line)
        label = label_by_alias.get(declaration.alias) if declaration is not None else None
        relabelled.append(relabelled_declaration(line, label) if label else line)
    return "\n".join(relabelled)


def drawn_labels_by_instance(
    body: str,
    diagram_entities: Mapping[str, object] | None,
    entity_by_id: Mapping[str, EntityRecord],
) -> dict[str, str]:
    """What each instance is called in *body* as it stands, by instance id.

    Read off the declarations rather than derived from the elements, because a hand-laid body may
    call an element something its record does not say — and that is the label an editor has to show
    and carry forward, or a save that regenerates the body would silently revert it.
    """
    label_by_alias: dict[str, str] = {}
    for line in body.splitlines():
        declaration = alias_declared_on(line)
        if declaration is None:
            continue
        label = label_declared_on(line)
        if label:
            label_by_alias.setdefault(declaration.alias, label)
    return {
        instance_id: label_by_alias[alias]
        for instance_id, alias in _alias_by_instance(diagram_entities, entity_by_id).items()
        if alias in label_by_alias
    }
