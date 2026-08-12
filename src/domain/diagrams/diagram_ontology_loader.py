"""Loader for diagram type ontology.yaml files."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec, allowed_bindings_from_config
from src.domain.modules.bridges import BridgeDeclaration, bridges_from_config
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import (
    ConnectionTypeInfo,
    EntityTypeInfo,
    RequiredConnection,
    mapping_spec_from_config,
)
from src.domain.ontology_representation.relation_notation import parse_relation_notation
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet, permitted_connections_from_config
from src.domain.yaml_documents import parse_yaml


@dataclass(frozen=True)
class DiagramOntology:
    """Parsed content of a diagram type's ontology.yaml."""

    entity_types: dict[EntityTypeName, EntityTypeInfo]
    entity_type_properties: dict[str, dict[str, Any]]  # raw properties per entity type
    entity_type_managed_fields: dict[str, dict[str, str]]  # explicit managed-field descriptions per entity type
    connection_types: dict[ConnectionTypeName, ConnectionTypeInfo]
    permitted_relationships: PermittedRelationshipSet
    allowed_bindings: AllowedBindingsSpec = dataclasses.field(default_factory=AllowedBindingsSpec.empty)
    bridges: tuple[BridgeDeclaration, ...] = dataclasses.field(default_factory=tuple)


def load_diagram_ontology(path: Path) -> DiagramOntology:
    with path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = parse_yaml(fh) or {}

    raw_entity_types: dict[str, Any] = raw.get("entity_types") or {}
    entity_types = _parse_entity_types(raw_entity_types)
    entity_type_properties = {
        name: dict(cfg.get("properties") or {}) for name, cfg in raw_entity_types.items() if isinstance(cfg, dict)
    }
    entity_type_managed_fields = {
        name: {str(k): str(v) for k, v in cfg["managed_fields"].items()}
        for name, cfg in raw_entity_types.items()
        if isinstance(cfg, dict) and isinstance(cfg.get("managed_fields"), dict)
    }
    connection_types = _parse_connection_types(raw.get("connection_types") or {})
    permitted = _parse_permitted_relationships(
        raw.get("permitted_relationships") or [],
        entity_types,
        connection_types,
    )
    allowed_bindings = allowed_bindings_from_config(raw.get("allowed_bindings"))
    bridges = bridges_from_config(raw.get("bridges"))
    return DiagramOntology(
        entity_types=entity_types,
        entity_type_properties=entity_type_properties,
        entity_type_managed_fields=entity_type_managed_fields,
        connection_types=connection_types,
        permitted_relationships=permitted,
        allowed_bindings=allowed_bindings,
        bridges=bridges,
    )


def _parse_entity_types(raw: dict[str, Any]) -> dict[EntityTypeName, EntityTypeInfo]:
    out: dict[EntityTypeName, EntityTypeInfo] = {}
    for name, info in raw.items():
        cfg: dict[str, Any] = info or {}
        req_conns = tuple(
            _parse_required_connection(rc) for rc in (cfg.get("required_connections") or []) if isinstance(rc, dict)
        )
        max_val = cfg.get("max")
        out[EntityTypeName(name)] = EntityTypeInfo(
            artifact_type=str(name),
            prefix="",
            hierarchy=(),
            classes=tuple(str(c) for c in cfg.get("classes", ())),
            create_when=str(cfg.get("create_when") or ""),
            never_create_when=str(cfg.get("never_create_when") or ""),
            required_connections=req_conns,
            min=int(cfg.get("min", 0)),
            max=None if max_val is None else int(max_val),
            permitted_mappings=mapping_spec_from_config(cfg.get("permitted_mappings")),
            mapping_required=bool(cfg.get("mapping_required", False)),
            identity_scope=str(cfg.get("identity_scope") or "diagram"),  # type: ignore[arg-type]
            id_prefix=(str(cfg["id_prefix"]) if cfg.get("id_prefix") else None),
        )
    return out


def _parse_required_connection(cfg: dict[str, Any]) -> RequiredConnection:
    raw_card = cfg.get("cardinality") or [1, 1]
    card_min = int(raw_card[0]) if raw_card else 1
    card_max: int | None = int(raw_card[1]) if len(raw_card) > 1 and raw_card[1] is not None else None
    return RequiredConnection(
        connection_type=str(cfg["connection_type"]),
        target=str(cfg["target"]),
        cardinality_min=card_min,
        cardinality_max=card_max,
    )


def _parse_connection_types(raw: dict[str, Any]) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
    out: dict[ConnectionTypeName, ConnectionTypeInfo] = {}
    for name, info in raw.items():
        cfg: dict[str, Any] = info or {}
        embedding = str(cfg.get("embedding") or "none")
        out[ConnectionTypeName(name)] = ConnectionTypeInfo(
            artifact_type=str(name),
            conn_lang="diagram",
            embedding=embedding,  # type: ignore[arg-type]
            embed_key=str(cfg["embed_key"]) if cfg.get("embed_key") else None,
            cascade_delete_source=bool(cfg.get("cascade_delete_source", False)),
            classes=tuple(str(c) for c in cfg.get("classes", ())),
            symmetric=bool(cfg.get("symmetric", False)),
            puml_arrow=str(cfg["puml_arrow"]) if cfg.get("puml_arrow") else "-->",
            notation=parse_relation_notation(cfg.get("notation")),
            show_stereotype=bool(cfg.get("show_stereotype", True)),
            relationship_kind=str(cfg["relationship_kind"]) if cfg.get("relationship_kind") else None,
        )
    return out


def _parse_permitted_relationships(
    rules: list[Any],
    entity_types: dict[EntityTypeName, EntityTypeInfo],
    connection_types: dict[ConnectionTypeName, ConnectionTypeInfo],
) -> PermittedRelationshipSet:
    class_members: dict[str, list[str]] = {}
    for ename, info in entity_types.items():
        for cls in info.classes:
            class_members.setdefault(cls, []).append(str(ename))

    expanded: list[list[Any]] = []
    for rule in rules:
        if not isinstance(rule, list) or len(rule) < 3:
            continue
        src_raw, tgt_raw, conn_list = rule[0], rule[1], rule[2]
        sources = _expand_class_ref(src_raw, class_members)
        targets = _expand_class_ref(tgt_raw, class_members)
        for src in sources:
            for tgt in targets:
                expanded.append([src, tgt, conn_list])

    return permitted_connections_from_config(expanded)  # type: ignore[arg-type]


def _expand_class_ref(ref: str, class_members: dict[str, list[str]]) -> list[str]:
    if isinstance(ref, str) and ref.startswith("@"):
        return list(class_members.get(ref[1:], []))
    return [str(ref)]
