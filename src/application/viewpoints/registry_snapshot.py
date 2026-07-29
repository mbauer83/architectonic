"""Builds a ``RegistrySnapshot`` from the real runtime catalogs
and a repository's ``.arch-repo/schemata/`` files — the wiring the pure criteria evaluator
needs to tell a known attribute path from schema drift, and to normalize incident-condition
direction against symmetric connection types.

Attribute declarations are scoped per (entity type, specialization) but the evaluator's
attribute-path namespace is deliberately flat (one namespace, used
everywhere a path appears") — so this merges every entity/connection type's effective
attribute schema, across every repo tier, into the two flat maps ``RegistrySnapshot`` wants.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from src.application.artifact_schema import compute_effective_attribute_schema, load_connection_metadata_schema
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND, declares_ordinal
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot

_DEFAULT_ATTRIBUTE_TYPE = "string"
_DEFAULT_DERIVATION_MAX_HOPS = 4
_DEFAULT_DERIVATION_MAX_RELATIONSHIPS = 2000
_DEFAULT_DERIVATION_TIME_BUDGET_SECONDS = 2.0


def _property_types(schema: Mapping[str, object] | None) -> dict[str, str]:
    if schema is None:
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    types: dict[str, str] = {}
    for name, prop in properties.items():
        types[str(name)] = _declared_kind(prop)
    return types


def _declared_kind(prop: object) -> str:
    """The scalar kind an attribute-schema property resolves to.

    A declared level of measurement wins over the JSON-Schema type, because it is the more
    specific statement: an ordinal is written as a string enum, and treating it as a plain
    string would order it alphabetically.
    """
    if not isinstance(prop, Mapping):
        return _DEFAULT_ATTRIBUTE_TYPE
    if declares_ordinal(prop):
        return ORDINAL_KIND
    return str(prop.get("type", _DEFAULT_ATTRIBUTE_TYPE))


def _property_enums(schema: Mapping[str, object] | None) -> dict[str, tuple[str, ...]]:
    """Enumerable value sets declared per attribute via JSON-schema ``enum``. Only string
    enums are surfaced (the criteria value picker is string-shaped); a non-list or empty
    ``enum`` is skipped, leaving that attribute a free-text value input."""
    if schema is None:
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    enums: dict[str, tuple[str, ...]] = {}
    for name, prop in properties.items():
        if not isinstance(prop, Mapping):
            continue
        values = prop.get("enum")
        if isinstance(values, Sequence) and not isinstance(values, str | bytes) and len(values) > 0:
            enums[str(name)] = tuple(str(v) for v in values)
    return enums


def _entity_attribute_schema_facets(
    runtime_catalogs: RuntimeCatalogs, repo_roots: Sequence[Path]
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    types: dict[str, str] = {}
    enums: dict[str, tuple[str, ...]] = {}
    for entity_type in runtime_catalogs.ontology.all_entity_type_names():
        slugs = ("", *(spec.slug for spec in runtime_catalogs.specializations.for_type("entity", entity_type)))
        for repo_root in repo_roots:
            for slug in slugs:
                schema, _conflicts = compute_effective_attribute_schema(
                    repo_root,
                    entity_type,
                    [slug],
                    specialization_catalog=runtime_catalogs.specializations,
                    profile_registry=runtime_catalogs.profiles,
                )
                types.update(_property_types(schema))
                enums.update(_property_enums(schema))
    return types, enums


def _connection_attribute_schema_facets(
    runtime_catalogs: RuntimeCatalogs, repo_roots: Sequence[Path]
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    types: dict[str, str] = {}
    enums: dict[str, tuple[str, ...]] = {}
    for connection_type in runtime_catalogs.ontology.all_connection_type_names():
        for repo_root in repo_roots:
            schema = load_connection_metadata_schema(repo_root, connection_type)
            types.update(_property_types(schema))
            enums.update(_property_enums(schema))
    return types, enums


def build_registry_snapshot(
    runtime_catalogs: RuntimeCatalogs,
    repo_roots: Sequence[Path],
    *,
    derivation_max_hops: int = _DEFAULT_DERIVATION_MAX_HOPS,
    derivation_max_relationships: int = _DEFAULT_DERIVATION_MAX_RELATIONSHIPS,
    derivation_time_budget_seconds: float = _DEFAULT_DERIVATION_TIME_BUDGET_SECONDS,
) -> RegistrySnapshot:
    """One snapshot for the lifetime of a verification run — callers should build this once
    (e.g. a ``functools.cached_property``) rather than per file, since it scans every entity
    type's effective attribute schema across every repo tier."""
    known_entity_types = runtime_catalogs.ontology.all_entity_type_names()
    known_connection_types = runtime_catalogs.ontology.all_connection_type_names()
    known_specialization_slugs = frozenset(spec.slug for spec in runtime_catalogs.specializations.entries)
    symmetric_connection_types = frozenset(
        ct for ct in known_connection_types if runtime_catalogs.connections.is_symmetric(ct)
    )
    entity_attribute_types, entity_attribute_enums = _entity_attribute_schema_facets(runtime_catalogs, repo_roots)
    connection_attribute_types, connection_attribute_enums = _connection_attribute_schema_facets(
        runtime_catalogs, repo_roots
    )
    return RegistrySnapshot(
        known_entity_types=known_entity_types,
        known_connection_types=known_connection_types,
        known_specialization_slugs=known_specialization_slugs,
        entity_attribute_types=entity_attribute_types,
        connection_attribute_types=connection_attribute_types,
        entity_attribute_enums=entity_attribute_enums,
        connection_attribute_enums=connection_attribute_enums,
        symmetric_connection_types=symmetric_connection_types,
        entity_type_infos=runtime_catalogs.ontology.all_entity_types(),
        derivation_catalog=runtime_catalogs.module_catalog,
        derivation_max_hops=derivation_max_hops,
        derivation_max_relationships=derivation_max_relationships,
        derivation_time_budget_seconds=derivation_time_budget_seconds,
    )
