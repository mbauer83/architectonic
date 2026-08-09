from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.domain.diagrams.diagram_entities_schema import derive_diagram_entities_schema
from src.domain.diagrams.diagram_ontology_loader import DiagramOntology, load_diagram_ontology
from src.domain.diagrams.diagram_ontology_merge import merge_ontology_into_diagram_only_types
from src.domain.modules.bridges import BridgeDeclaration
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
    diagram_type_ui_config_from_mapping,
    element_classes_from_config,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

_OWN_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class _ActivityDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        merged_config = merge_ontology_into_diagram_only_types(config, ontology)
        self._config = merged_config
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = element_classes_from_config(config)
        self._ui_config = diagram_type_ui_config_from_mapping(
            merged_config,
            default_label="Activity Diagram",
        )
        self._renderer = ActivityPumlRenderer(config)

    @property
    def element_classes(self) -> dict[str, ElementClassInfo]:
        return self._element_classes

    @property
    def name(self) -> DiagramTypeName:
        return self._name

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _OWN_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return dict(self._ontology.connection_types)

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return self._ontology.permitted_relationships

    @property
    def bridges(self) -> tuple[BridgeDeclaration, ...]:
        return self._ontology.bridges

    @property
    def renderer(self) -> DiagramRenderer:
        return self._renderer

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        g: dict[str, Any] = self._config.get("guidance") or {}
        own_types = self._ui_config.diagram_only_types
        ab = self._ontology.allowed_bindings
        return DiagramTypeWriteGuidance(
            when_to_use=str(g.get("when_to_use") or ""),
            when_not_to_use=str(g.get("when_not_to_use") or ""),
            diagram_entities_schema=derive_diagram_entities_schema(own_types),
            own_entity_types=own_types,
            puml_notes=(
                "Steps and lanes go in `diagram_entities`; the flow between them goes in"
                " `diagram_connections`, as objects of the form"
                " {id, conn_type, source, target} — the same shape the file persists. Declaring"
                " steps without connections yields a diagram of one step and a warning per orphan.",
                "Every step needs a `step-in-lane` connection naming its swimlane, including"
                " decisions and forks. A step without one is emitted with a WARNING comment and"
                " lands in whichever lane was last active.",
                "A decision needs three edges, not two: `step-then` to the first step of the true"
                " branch, `step-else` to the first step of the false branch, and a `step-flow` to"
                " the step the branches merge back into. Omitting the third leaves the branches"
                " dangling.",
                "Notes attach with `step-note-of`, whose *source* is the note and whose *target* is"
                " the step it annotates.",
                "Long step labels widen their whole swimlane, so prefer short imperative labels and"
                " put the nuance in a note. `layout.wrap_width` bounds this, but wrapping every"
                " label is not a substitute for writing short ones.",
                "Minimal example — two lanes, one decision:\n"
                "  diagram_entities: {swimlane: [{id: you}, {id: system}],\n"
                "    action: [{id: a1, label: Ask}, {id: a2, label: Answer}],\n"
                "    decision: [{id: d1, condition: Known?, then_label: yes, else_label: no}]}\n"
                "  diagram_connections: [\n"
                "    {id: l1, conn_type: step-in-lane, source: a1, target: you},\n"
                "    {id: l2, conn_type: step-in-lane, source: d1, target: you},\n"
                "    {id: l3, conn_type: step-in-lane, source: a2, target: system},\n"
                "    {id: f1, conn_type: step-flow, source: a1, target: d1},\n"
                "    {id: t1, conn_type: step-then, source: d1, target: a2}]",
            ),
            allowed_bindings=ab if not ab.is_empty() else None,
        )


_PACKAGE_DIR = Path(__file__).parent
_config = _load_config(_PACKAGE_DIR)
_ontology = load_diagram_ontology(_PACKAGE_DIR / "ontology.yaml")
module: DiagramTypeModule = _ActivityDiagramType(_config, _ontology)
