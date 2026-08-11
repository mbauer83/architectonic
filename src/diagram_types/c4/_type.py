"""Shared loader for diagram-owned C4 diagram types."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.modules.module_registry import ModuleRegistry
    from src.domain.relationships.derivation_types import ModelQuery
    from src.domain.viewpoints.view_derivations import DerivationSelection
    from src.domain.viewpoints.view_projection import ViewProjectionResult


# Import engine module to trigger strategy registration as a side effect.
import src.diagram_types.c4._projection  # noqa: F401
from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.c4.renderer import C4PumlRenderer
from src.domain.concept_scope import ConceptScope
from src.domain.diagrams.diagram_entities_schema import derive_diagram_entities_schema
from src.domain.diagrams.diagram_ontology_loader import DiagramOntology, load_diagram_ontology
from src.domain.diagrams.diagram_ontology_merge import merge_ontology_into_diagram_only_types
from src.domain.diagrams.diagram_type_config import puml_notes_from_config
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
from src.domain.relationships.permitted_mappings import concept_scope_for_diagram_only_types
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.yaml_documents import parse_yaml

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}

_C4_OWN_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {
    ConnectionTypeName("c4-uses"): ConnectionTypeInfo(
        artifact_type="c4-uses",
        conn_lang="c4",
        symmetric=False,
        puml_arrow="-->",
        classes=(),
        hierarchy_priority=None,
        hierarchy_label="uses",
    ),
}


def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


class _C4DiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        self._config = merge_ontology_into_diagram_only_types(config, ontology)
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = element_classes_from_config(config)
        self._ui_config = diagram_type_ui_config_from_mapping(
            self._config,
            default_label=str(config.get("ui", {}).get("label") or self._name).replace("-", " ").title(),
        )
        self._renderer = C4PumlRenderer(self._config, person_archimate_types=_person_archimate_types(ontology))

    @property
    def element_classes(self) -> dict[str, ElementClassInfo]:
        return self._element_classes

    @property
    def name(self) -> DiagramTypeName:
        return self._name

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    def concept_scope(self, registry: ModuleRegistry | None = None) -> ConceptScope:
        reg = registry if registry is not None else _registry()
        entity_scope = concept_scope_for_diagram_only_types(self._ui_config.diagram_only_types, reg)
        return ConceptScope(
            entity_types=entity_scope.entity_types,
            connection_types=frozenset(reg.all_connection_types()),
        )

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _EMPTY_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return _C4_OWN_CONNECTION_TYPES

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
        schema = self._augment_schema(derive_diagram_entities_schema(own_types))
        ab = self._ontology.allowed_bindings
        return DiagramTypeWriteGuidance(
            when_to_use=str(g.get("when_to_use") or ""),
            when_not_to_use=str(g.get("when_not_to_use") or ""),
            diagram_entities_schema=schema,
            own_entity_types=own_types,
            puml_notes=puml_notes_from_config(self._config),
            allowed_bindings=ab if not ab.is_empty() else None,
        )

    def _augment_schema(self, schema: dict[str, Any] | None) -> dict[str, Any]:
        base: dict[str, Any] = dict(schema) if schema else {"type": "object", "properties": {}}
        props: dict[str, Any] = dict(base.get("properties") or {})
        c4_cfg: dict[str, Any] = self._config.get("c4") or {}
        scope_type = str(c4_cfg.get("scope_entity_type") or "entity")
        props["_scope_entity_id"] = {
            "type": "string",
            "description": (
                f"entity_id of the {scope_type} model entity this diagram is scoped to. "
                "Set to enable model-backed mode (entities and connections auto-derived from ArchiMate graph). "
                "Omit for standalone mode (explicit diagram entities and c4-uses connections)."
            ),
        }
        props["_included_entity_ids"] = {
            "type": "array", "items": {"type": "string"},
            "description": (
                "entity_ids to include from the ArchiMate graph (model-backed only). "
                "Omit to include all connected entities. Use the smaller of included or excluded."
            ),
        }
        props["_excluded_entity_ids"] = {
            "type": "array", "items": {"type": "string"},
            "description": (
                "entity_ids to exclude from auto-derived neighbours (model-backed only). "
                "Mutually exclusive with _included_entity_ids. Use the smaller set."
            ),
        }
        return {**base, "properties": props}

    def resolve_diagram_entities(
        self, parsed_source: dict[str, Any], diagram_entities: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Re-hydrate what the persist path stripped, so a reader sees what the author wrote.

        `strip_diagram_shorthand` removes `entity_id` from every item and `_scope_entity_id` from the
        top level, because the top-level `bindings:` block is canonical *on disk*. Nothing put them
        back on the way out, so every consumer downstream of the read envelope saw items with no
        model correspondence at all: element selection matched nothing, drill-down badges never
        appeared, and the editor's scope detection (`r.scope && r.entity_id`) silently failed.

        Serving them back is the smallest correct fix, and it is this hook's existing job — it
        already did exactly this for `_scope_entity_id`. Disk keeps one canonical form; the wire
        carries the convenience fields every reader was already written against.

        A declared-field override rather than a module extra, which is why it is this hook: the read
        envelope declares ``diagram_entities``, and filling it in is not the same act as adding a key
        of one's own.
        """
        from src.diagram_types.c4._navigation import resolve_scope_entity_id  # noqa: PLC0415
        from src.domain.diagrams.bindings import element_entity_ids  # noqa: PLC0415

        frontmatter: dict[str, Any] = parsed_source.get("frontmatter") or {}
        bindings = frontmatter.get("bindings")
        bound = element_entity_ids(bindings)

        rehydrated: dict[str, Any] = {}
        changed = False
        for key, value in diagram_entities.items():
            if key.startswith("_") or not isinstance(value, list):
                rehydrated[key] = value
                continue
            items: list[Any] = []
            for item in value:
                entity_id = bound.get(str(item.get("id") or "")) if isinstance(item, dict) else None
                if entity_id and not item.get("entity_id"):
                    items.append({**item, "entity_id": entity_id})
                    changed = True
                else:
                    items.append(item)
            rehydrated[key] = items

        # Both shapes: a standalone diagram's scope item is bound element-level, a model-backed one
        # carries a diagram-level `scoped-by`. Reading only the second left the editor's scope
        # detection blind for everything authored the standalone way.
        scope_id = str(diagram_entities.get("_scope_entity_id") or "") or resolve_scope_entity_id(
            diagram_entities, bindings
        )
        if scope_id and scope_id != diagram_entities.get("_scope_entity_id"):
            rehydrated["_scope_entity_id"] = scope_id
            changed = True
        # Merged into what the caller assembled rather than rebuilt from the frontmatter: the
        # caller's value carries the diagram's local `_connections`, and rebuilding dropped them.
        return rehydrated if changed else None

    def build_context_extras(
        self,
        repo: Any,
        diagram_id: str,
        diagram_entities: dict[str, Any],
    ) -> dict[str, Any]:
        from src.diagram_types.c4._navigation import build_c4_navigation  # noqa: PLC0415

        nav = build_c4_navigation(repo, diagram_id, str(self._name), diagram_entities)
        return {"c4_navigation": nav} if nav is not None else {}

    def project_view(
        self,
        diagram_type: str,
        diagram_entities: Mapping[str, object],
        query: ModelQuery,
    ) -> ViewProjectionResult | None:
        from src.diagram_types.c4._projection import project_c4  # noqa: PLC0415
        from src.domain.viewpoints.view_derivations import SourceModelSnapshot, ViewDerivation  # noqa: PLC0415
        from src.domain.viewpoints.view_projection import ViewProjectionResult  # noqa: PLC0415

        scope_id = str(diagram_entities.get("_scope_entity_id") or "").strip()
        if not scope_id:
            return None

        internal_c4_type = self._internal_c4_type()
        scope_entity_type = self._scope_entity_type()
        projection = project_c4(
            diagram_type, scope_id, query,
            internal_c4_type=internal_c4_type,
            scope_entity_type=scope_entity_type,
            person_archimate_types=self._renderer._person_archimate_types,
        )
        derivation = ViewDerivation(
            id="__preview__",
            strategy="c4.scope-projection",
            strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both", root_entity_id=scope_id),
            parameters={
                "diagram_type": diagram_type,
                "internal_c4_type": internal_c4_type,
                "scope_entity_type": scope_entity_type,
                "person_archimate_types": sorted(self._renderer._person_archimate_types),
            },
            selection=_selection_from_entities(diagram_entities),
        )
        return ViewProjectionResult(derivation=derivation, items=tuple(projection.to_view_items()))

    def _c4_config(self) -> Mapping[str, Any]:
        raw = self._config.get("c4")
        return raw if isinstance(raw, Mapping) else {}

    def _internal_c4_type(self) -> str:
        internal_types = list(self._c4_config().get("internal_entity_types") or [])
        return str(internal_types[0]) if internal_types else "container"

    def _scope_entity_type(self) -> str:
        return str(self._c4_config().get("scope_entity_type") or "software-system")


def _selection_from_entities(entities: Mapping[str, object]) -> DerivationSelection | None:
    from src.domain.viewpoints.view_derivations import DerivationSelection  # noqa: PLC0415

    raw_included = entities.get("_included_entity_ids")
    raw_excluded = entities.get("_excluded_entity_ids")
    if isinstance(raw_included, list) and raw_included:
        return DerivationSelection(included_entity_ids=tuple(str(x) for x in raw_included))
    if isinstance(raw_excluded, list) and raw_excluded:
        return DerivationSelection(excluded_entity_ids=tuple(str(x) for x in raw_excluded))
    return None


def _person_archimate_types(ontology: DiagramOntology) -> frozenset[str]:
    person_et = ontology.entity_types.get(EntityTypeName("person"))
    if person_et is None:
        return frozenset()
    return frozenset(person_et.permitted_mappings.entity_types)


def load_c4_diagram_type(package_dir: Path) -> DiagramTypeModule:
    config = _load_config(package_dir)
    ontology = load_diagram_ontology(package_dir / "ontology.yaml")
    return _C4DiagramType(config, ontology)
