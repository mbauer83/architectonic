"""Connection-type guidance: specialization enumeration plus, when a repo root is known,
the EFFECTIVE merged metadata schema each (connection-type, specialization) pair authors
against.

Entities get their effective schema from ``GET /api/entity-schemata``; connections have no
such endpoint, so the authoring-guidance payload carries theirs. Both transports (REST and
MCP) call the same builder, so neither can offer a shape the other lacks.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.application.artifact_schema import (
    attribute_descriptors,
    compute_effective_connection_metadata_schema,
    schema_all_properties,
    schema_required_properties,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo


def serialize_specialization(info: SpecializationInfo) -> dict[str, object]:
    entry: dict[str, object] = {
        "slug": info.slug,
        "name": info.name,
        "description": info.description,
        "create_when": info.create_when,
        "never_create_when": info.never_create_when,
    }
    if info.notation.icon or info.notation.color:
        notation = {k: v for k, v in (("icon", info.notation.icon), ("color", info.notation.color)) if v}
        entry["notation"] = notation
    return entry


def connection_type_guidance(
    specialization_catalog: SpecializationCatalog,
    *,
    profile_registry: ProfileRegistry = ProfileRegistry.empty(),
    repo_root: Path | None = None,
    connection_types: Mapping[str, ConnectionTypeInfo],
) -> list[dict[str, object]]:
    """Per-connection-type creation, specialization, and effective metadata-schema guidance.

    A type appears when it has anything to say: imported ``create_when``/``never_create_when``
    guidance, specializations, or a base metadata schema. Types with none of the three remain
    omitted, keeping the response compact while ensuring every answerable relationship and every
    editable schema reaches authoring clients.

    With ``repo_root``, each entry also carries the effective metadata schema: the
    type-level one under ``metadata_schema``, and each specialization's merged schema under
    its own ``metadata_schema``, alongside ``quarantined`` — the same derived read of the
    same conflicts channel the entity schema endpoint exposes, so an authoring surface can
    disable a pair it must not write.
    """
    entries: list[dict[str, object]] = []
    for name, info in sorted(connection_types.items()):
        specializations = specialization_catalog.for_type("connection", name)
        base_schema = (
            _schema_block(repo_root, name, "", specialization_catalog, profile_registry)
            if repo_root is not None
            else None
        )
        has_guidance = bool(info.create_when or info.never_create_when)
        if not has_guidance and not specializations and not (base_schema and base_schema["schema"] is not None):
            continue
        entry: dict[str, object] = {
            "name": name,
            "create_when": info.create_when,
            "never_create_when": info.never_create_when,
            "specializations": [
                _specialization_entry(spec, name, specialization_catalog, profile_registry, repo_root)
                for spec in specializations
            ],
        }
        if base_schema is not None:
            entry["metadata_schema"] = base_schema
        entries.append(entry)
    return entries


def _specialization_entry(
    info: SpecializationInfo,
    connection_type: str,
    specialization_catalog: SpecializationCatalog,
    profile_registry: ProfileRegistry,
    repo_root: Path | None,
) -> dict[str, object]:
    entry = serialize_specialization(info)
    if repo_root is not None:
        entry["metadata_schema"] = _schema_block(
            repo_root, connection_type, info.slug, specialization_catalog, profile_registry
        )
    return entry


def _schema_block(
    repo_root: Path,
    connection_type: str,
    specialization_slug: str,
    specialization_catalog: SpecializationCatalog,
    profile_registry: ProfileRegistry,
) -> dict[str, Any]:
    schema, conflicts = compute_effective_connection_metadata_schema(
        repo_root,
        connection_type,
        [specialization_slug],
        specialization_catalog=specialization_catalog,
        profile_registry=profile_registry,
    )
    return {
        "schema": schema,
        "properties": schema_all_properties(schema) if schema else [],
        "required": schema_required_properties(schema) if schema else [],
        "descriptors": attribute_descriptors(schema) if schema else {},
        "conflicts": conflicts,
        # Derived from the SAME conflicts channel, never a parallel one: true means the
        # write boundary refuses this pair.
        "quarantined": bool(conflicts),
    }
