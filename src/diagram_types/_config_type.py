"""Helpers for config-backed ontology-bound diagram types."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._base import DiagramTypeBase
from src.domain.concept_scope import ConceptScope, HierarchyPredicate
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
    OntologyModule,
    diagram_type_ui_config_from_mapping,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}


def _build_concept_scope(filter_cfg: dict[str, Any], ontology: OntologyModule) -> ConceptScope:
    hierarchy_cfg = filter_cfg.get("hierarchy_level")
    class_set = frozenset(str(c) for c in filter_cfg.get("classes", ()))
    type_set = frozenset(str(t) for t in filter_cfg.get("entity_types", ()))
    hierarchy_predicates: tuple[HierarchyPredicate, ...] = ()
    if hierarchy_cfg:
        hierarchy_predicates = (
            HierarchyPredicate(
                index=int(hierarchy_cfg["index"]),
                values=frozenset(str(v) for v in hierarchy_cfg.get("values", ())),
            ),
        )
    return ConceptScope(
        entity_types=frozenset(EntityTypeName(t) for t in type_set) if type_set else None,
        entity_class_predicates=(class_set,) if class_set else (),
        hierarchy_predicates=hierarchy_predicates,
        connection_types=frozenset(ontology.connection_types),
    )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_ontology_module(package_name: str) -> OntologyModule:
    imported = importlib.import_module(f"src.ontologies.{package_name}")
    module = getattr(imported, "module", None)
    if module is None:
        raise ValueError(f"Ontology package 'src.ontologies.{package_name}' does not export a 'module' object")
    return module


class _ConfiguredOntologyDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: OntologyModule) -> None:
        self._config = config
        self._ontology = ontology
        self._name = DiagramTypeName(str(config["name"]))
        self._ui_config = diagram_type_ui_config_from_mapping(
            config,
            default_label=str(self._name).replace("-", " ").title(),
        )
        filter_cfg: dict[str, Any] = config.get("filter", {})
        self._concept_scope = _build_concept_scope(filter_cfg, ontology)
        hierarchy_values = filter_cfg.get("hierarchy_level", {}).get("values", [])
        self._accepted_domains: tuple[str, ...] = tuple(str(v) for v in hierarchy_values)

    @property
    def name(self) -> DiagramTypeName:
        return self._name

    @property
    def primary_ontology(self):  # type: ignore[override]
        return self._ontology

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _EMPTY_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return _EMPTY_CONNECTION_TYPES

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def renderer(self) -> DiagramRenderer:
        from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer  # noqa: PLC0415

        return GenericPumlRenderer(self._config)

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        g: dict[str, Any] = self._config.get("guidance") or {}
        return DiagramTypeWriteGuidance(
            when_to_use=str(g.get("when_to_use") or ""),
            when_not_to_use=str(g.get("when_not_to_use") or ""),
            accepted_domains=self._accepted_domains,
        )


def load_configured_diagram_type(package_dir: Path) -> DiagramTypeModule:
    """Load one config-backed diagram type that binds to a named ontology package."""
    config = _load_config(package_dir)
    ontology_name = str(config.get("ontology") or "").strip()
    if not ontology_name:
        raise ValueError(f"Diagram type config at {package_dir / 'config.yaml'} must define an 'ontology' package")
    return _ConfiguredOntologyDiagramType(config, _load_ontology_module(ontology_name))
