"""What an ontology says about a diagram type's own constructs, in configuration form.

The inverse of :func:`diagram_type_config.diagram_type_ui_config_from_mapping`. A module ships a
``config.yaml`` describing how its own constructs are authored; the ontology beside it declares what
they *are* — their classes, their cardinality, what they may map onto, what they must connect to. The
two are folded together before the config is parsed, so the parsed result carries both.

Four modules had a copy of this fold, and they were near-identical: ``sequence`` and ``activity``
byte-for-byte apart from a docstring, ``datatype`` adding two lines, ``c4`` missing one block. The
differences were not decisions. ``c4`` dropped ``required_connections`` and three modules dropped
``identity_scope`` and ``id_prefix``, all of which the parsed config declares and the served DTO
requires — the omissions were invisible because every affected type happened to hold the parser's
default. ``c4`` also spelled a generated label better than its three siblings did.

So it is one fold, emitting everything the ontology can say. A module that adds an own construct with
a non-default identity scope now has it published, wherever the module is; before, that depended on
which copy it had inherited.

**Direction of ownership.** The fold names no module's vocabulary — it reads an ``EntityTypeInfo``
and writes the keys the config parser reads — which is why it can live in the core the modules
register with rather than in any one of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.diagrams.diagram_ontology_loader import DiagramOntology
from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo


def _required_connections_config(ont_et: EntityTypeInfo) -> list[dict[str, Any]]:
    return [
        {
            "connection_type": rc.connection_type,
            "target": rc.target,
            "cardinality": [rc.cardinality_min, rc.cardinality_max],
        }
        for rc in ont_et.required_connections
    ]


def ontology_fields_for_own_type(
    ont_et: EntityTypeInfo,
    ontology: DiagramOntology,
) -> dict[str, Any]:
    """Everything the ontology states about one own construct, keyed as the config parser reads it.

    Returned rather than assigned into a caller's dict: the caller merges it over its own entry, so
    precedence — ontology wins — is visible at the merge rather than hidden in a mutation. The keys
    that are *conditionally* present are the ones where an empty ontology value must not overwrite a
    value the module's ``config.yaml`` supplied.
    """
    fields: dict[str, Any] = {
        "classes": list(ont_et.classes),
        "create_when": ont_et.create_when,
        "never_create_when": ont_et.never_create_when,
        "min": ont_et.min,
        "max": ont_et.max,
        "mapping_required": ont_et.mapping_required,
        "identity_scope": ont_et.identity_scope,
    }
    if ont_et.permitted_mappings.has_any():
        fields["permitted_mappings"] = ont_et.permitted_mappings.as_config()
    raw_properties = ontology.entity_type_properties.get(str(ont_et.artifact_type))
    if raw_properties:
        fields["properties"] = raw_properties
    raw_managed = ontology.entity_type_managed_fields.get(str(ont_et.artifact_type))
    if raw_managed:
        fields["managed_fields"] = raw_managed
    if ont_et.required_connections:
        fields["required_connections"] = _required_connections_config(ont_et)
    if ont_et.id_prefix is not None:
        fields["id_prefix"] = ont_et.id_prefix
    return fields


def _generated_label(entity_type: EntityTypeName) -> str:
    """A readable label for a type the ontology declares and the config does not mention.

    Hyphens become spaces before title-casing: ``software-system`` is "Software System", not
    "Software-System". Three of the four copies title-cased the raw name, which is the same answer
    for a single-word type and a worse one for every other.
    """
    return str(entity_type).replace("-", " ").title()


def merge_ontology_into_diagram_only_types(
    config: Mapping[str, Any],
    ontology: DiagramOntology,
) -> dict[str, Any]:
    """``config`` with its ``ui.diagram_only_types`` completed from ``ontology``.

    Every entry the config declares gains the ontology's statement about it, and every type the
    ontology declares that the config does not mention gains an entry of its own — a module need not
    restate a construct in two files to have it authorable.
    """
    ui: dict[str, Any] = dict(config.get("ui") or {})
    declared: list[Any] = list(ui.get("diagram_only_types") or [])
    merged: list[Any] = []
    seen: set[str] = set()

    for entry in declared:
        if not isinstance(entry, Mapping):
            merged.append(entry)
            continue
        entity_type = str(entry.get("entity_type") or "")
        seen.add(entity_type)
        ont_et = ontology.entity_types.get(EntityTypeName(entity_type))
        merged.append(
            dict(entry)
            if ont_et is None
            else {**entry, **ontology_fields_for_own_type(ont_et, ontology)}
        )

    for entity_type_name, ont_et in ontology.entity_types.items():
        if str(entity_type_name) in seen:
            continue
        merged.append({
            "entity_type": str(entity_type_name),
            "label": _generated_label(entity_type_name),
            **ontology_fields_for_own_type(ont_et, ontology),
        })

    return {**config, "ui": {**ui, "diagram_only_types": merged}}
