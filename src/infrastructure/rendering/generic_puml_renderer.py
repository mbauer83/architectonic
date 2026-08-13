"""Config-backed PlantUML renderer for diagram types."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.specializations import SpecializationCatalog, merge_specialization_catalogs
from src.infrastructure.rendering._archimate_includes import (
    ArchimateDeclarations,
    inject_archimate_includes,
)
from src.infrastructure.rendering._authored_grouping_rendering import render_authored_groupings
from src.infrastructure.rendering._component_canvas import render_component_canvas
from src.infrastructure.rendering._component_grouping import collect_subtree_aliases
from src.infrastructure.rendering._connection_line_rendering import render_connection_lines
from src.infrastructure.rendering._diagram_layout import build_branch_direction_hints, build_nested_layout_lines
from src.infrastructure.rendering.archimate_entity_declarations import (
    entity_declaration,
    entity_nest_declaration,
    grouping_key,
    grouping_stereotype,
    ordered_domains,
)
from src.infrastructure.rendering.archimate_occurrences import occurrence_entities
from src.infrastructure.rendering.archimate_relation_rendering import (
    format_multiplicity_label,
)
from src.infrastructure.rendering.diagram_connection_overlay import (
    endpoint_router,
    occurrence_alias_by_id,
)
from src.infrastructure.rendering.generic_puml_layout import build_generic_visual_nesting
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams
from src.infrastructure.rendering.puml_safety import (
    configured_puml_size_warning_threshold,
    warn_when_puml_exceeds_threshold,
)


def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


class GenericPumlRenderer:
    """Renderer for config-backed ArchiMate-style PlantUML diagrams."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config: dict[str, Any] = dict(config)

    def render_body(
        self,
        name: str,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
        edge_labels: dict[str, str] | None = None,
        label_attribute: str | None = None,
        authored_groupings: list[dict[str, object]] | None = None,
    ) -> str:
        del repo_root
        diagram_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-") or "diagram"
        lines: list[str] = [f"@startuml {diagram_name}"]
        for include in self._includes():
            lines.append(f"!include ../{include}")
        # An ArchiMate box is otherwise as wide as its widest unwrapped label — the same defect
        # every other diagram-owned type had, in the type that draws most of the repository.
        # Measured on `why-a-scratchpad`: 2545x798 unbounded against 1671x952 here, 34% narrower.
        # `layout.wrap_width: 0` opts a type out, as everywhere else.
        lines.extend(label_wrap_skinparams(self._config))
        lines.extend(["", f"title {name}", ""])

        entity_by_id = {entity.artifact_id: entity for entity in entities}
        render_entities = list(entities)
        occurrences = occurrence_entities(diagram_entities, entity_by_id)
        render_entities.extend(occurrences)

        alias_by_id = {
            entity.artifact_id: normalize_puml_alias(entity.display_alias)
            for entity in entities
            if entity.display_alias
        }
        entity_by_alias = {
            normalize_puml_alias(entity.display_alias): entity for entity in render_entities if entity.display_alias
        }

        domain_entities: dict[str, list[EntityRecord]] = defaultdict(list)
        for entity in render_entities:
            alias = normalize_puml_alias(entity.display_alias)
            if alias:
                domain_entities[grouping_key(entity, _registry())].append(entity)

        ordered_domain_keys = ordered_domains(domain_entities, _registry())
        single_domain = len(ordered_domain_keys) == 1
        flow_edges = [
            (src_alias, tgt_alias)
            for conn in connections
            if conn.conn_type in self._flow_conn_types()
            and (src_alias := alias_by_id.get(conn.source))
            and (tgt_alias := alias_by_id.get(conn.target))
        ]
        junction_aliases = {
            alias for alias, entity in entity_by_alias.items() if entity.artifact_type in self._junction_types()
        }
        layout_direction_hints: dict[tuple[str, str], str] = {}

        children_map, nested_aliases = self._build_visual_nesting(
            entities,
            connections,
            alias_by_id,
            entity_by_alias,
        )
        if authored_groupings:
            from src.infrastructure.rendering._authored_grouping_rendering import (  # noqa: PLC0415
                claimed_aliases,
                resolve_authored_members,
            )

            authored_member_aliases = claimed_aliases(
                resolve_authored_members(authored_groupings, render_entities)
            )
            # Declared membership in an authored group outranks modelled containment:
            # the relation stays in the model, but the picture keeps the user's box.
            nested_aliases -= authored_member_aliases
            for parent_alias in list(children_map):
                children_map[parent_alias] = [
                    child
                    for child in children_map[parent_alias]
                    if normalize_puml_alias(child.display_alias) not in authored_member_aliases
                ]
        for domain in list(domain_entities):
            domain_entities[domain] = [
                entity
                for entity in domain_entities[domain]
                if normalize_puml_alias(entity.display_alias) not in nested_aliases
            ]

        specialization_catalog = self._specialization_catalog()


        def render_entity(entity: EntityRecord, indent: str, chain_axis: str = "down") -> list[str]:
            """Render one item; its members chain along the axis PERPENDICULAR to
            *chain_axis* — the axis the item itself is arranged along — and that
            alternation applies recursively at every nesting level."""
            alias = normalize_puml_alias(entity.display_alias)
            if not alias:
                return []
            children = children_map.get(alias, [])
            decl_args = (entity, alias, _registry(), self._junction_types(), specialization_catalog)
            if not children:
                return [f"{indent}{entity_declaration(*decl_args, label_attribute=label_attribute)}"]
            inner = indent + "  "
            subtree = collect_subtree_aliases(entity, children_map)
            crossing_flow = any((src in subtree) != (tgt in subtree) for src, tgt in flow_edges)
            if crossing_flow:
                # The members are stations of a flow that passes THROUGH this box —
                # keep the through-flow's direction uniform instead of alternating.
                main_axis = chain_axis
            else:
                main_axis = "right" if chain_axis == "down" else "down"
            branch_axis = "down" if main_axis == "right" else "right"
            rendered = [f"{indent}{entity_nest_declaration(*decl_args, label_attribute=label_attribute)}"]
            for child in children:
                rendered.extend(render_entity(child, inner, main_axis))
            child_als = [normalize_puml_alias(child.display_alias) for child in children if child.display_alias]
            layout_direction_hints.update(
                build_branch_direction_hints(
                    child_aliases=child_als,
                    flow_edges=flow_edges,
                    junction_aliases=junction_aliases,
                    branch_axis=branch_axis,
                )
            )
            rendered.extend(
                build_nested_layout_lines(
                    child_aliases=child_als,
                    flow_edges=flow_edges,
                    junction_aliases=junction_aliases,
                    main_axis=main_axis,
                    branch_axis=branch_axis,
                    indent=inner,
                )
            )
            rendered.append(f"{indent}}}")
            return rendered

        connection_alias_pairs = frozenset(
            frozenset((src_alias, tgt_alias))
            for conn in connections
            if (src_alias := alias_by_id.get(conn.source)) and (tgt_alias := alias_by_id.get(conn.target))
            and src_alias != tgt_alias
        )
        if authored_groupings:
            lines.extend(
                render_authored_groupings(
                    authored_groupings,
                    render_entities=render_entities,
                    nested_aliases=nested_aliases,
                    domain_entities=domain_entities,
                    render_entity=render_entity,
                    # The vocabulary is the caller's: the grouping module names no domain, and this
                    # is the same pair of lookups the computed per-domain boxes below are built from.
                    domain_of=lambda entity: grouping_key(entity, _registry()),
                    stereotype_of=lambda domain: grouping_stereotype(self._config, domain),
                    direction_hints=layout_direction_hints,
                    connected_pairs=connection_alias_pairs,
                )
            )

        group_index_by_alias: dict[str, int] = {}
        domain_rank_by_alias: dict[str, int] = {}
        if single_domain and ordered_domain_keys:
            lines.insert(len(self._includes()) + 2, "top to bottom direction")
            lines.insert(len(self._includes()) + 3, "")
            domain = ordered_domain_keys[0]
            lines.extend(
                render_component_canvas(
                    top_entities=domain_entities[domain],
                    connections=connections,
                    alias_by_id=alias_by_id,
                    children_map=children_map,
                    flow_edges=flow_edges,
                    render_entity=render_entity,
                    group_index_by_alias=group_index_by_alias,
                    grouping=grouping_stereotype(self._config, domain),
                    nesting_conn_types=self._nesting_conn_types(),
                    registry=_registry(),
                    orders_upward=self._orders_upward,
                )
            )
        else:
            # Domain boxes stack in the ontology's declared layer order (motivation
            # above strategy above business/common/application/technology); the alias
            # lets a hidden chain enforce that rank on the canvas.
            previous_domain_alias: str | None = None
            previous_domain_members: set[str] = set()
            for domain_rank, domain in enumerate(ordered_domain_keys):
                for entity in domain_entities[domain]:
                    alias = normalize_puml_alias(entity.display_alias)
                    if alias:
                        domain_rank_by_alias[alias] = domain_rank
            # Only the domains with something left to show. Claiming empties a domain's list
            # rather than removing the domain, so one an authored grouping emptied still has a key
            # here — and drew an empty labelled box, which a cross-domain grouping makes routine.
            for domain in (key for key in ordered_domain_keys if domain_entities[key]):
                domain_alias = f"DOM_{re.sub(r'[^A-Za-z0-9_]', '_', domain)}"
                lines.append(
                    f'rectangle "{domain.title()}" <<{grouping_stereotype(self._config, domain)}>> '
                    f"as {domain_alias} {{"
                )
                # The same component canvas runs INSIDE each domain box — a domain used
                # to emit its members unordered, which erased the flow entirely.
                lines.extend(
                    render_component_canvas(
                        top_entities=domain_entities[domain],
                        connections=connections,
                        alias_by_id=alias_by_id,
                        children_map=children_map,
                        flow_edges=flow_edges,
                        render_entity=render_entity,
                        group_index_by_alias=group_index_by_alias,
                        grouping=grouping_stereotype(self._config, domain),
                        nesting_conn_types=self._nesting_conn_types(),
                        registry=_registry(),
                        orders_upward=self._orders_upward,
                        indent="  ",
                        alias_namespace=f"{re.sub(r'[^A-Za-z0-9_]', '_', domain)}_",
                    )
                )
                lines.append("}")
                domain_aliases = {
                    alias
                    for entity in domain_entities[domain]
                    if (alias := normalize_puml_alias(entity.display_alias))
                }
                domains_connected = any(
                    frozenset((prev, curr)) in connection_alias_pairs
                    for prev in previous_domain_members
                    for curr in domain_aliases
                )
                if previous_domain_alias and not domains_connected:
                    lines.append(f"{previous_domain_alias} -[hidden]down- {domain_alias}")
                previous_domain_alias = domain_alias
                previous_domain_members = domain_aliases
                lines.append("")

        conn_lines = render_connection_lines(
            connections,
            alias_by_id=alias_by_id,
            children_map=children_map,
            layout_direction_hints=layout_direction_hints,
            group_index_by_alias=group_index_by_alias,
            domain_rank_by_alias=domain_rank_by_alias,
            specialization_catalog=specialization_catalog,
            edge_labels=edge_labels,
            nesting_conn_types=self._nesting_conn_types(),
            connection_info=self._connection_info,
            visible_label=lambda conn: self.visible_connection_label(conn, diagram_connections),
            endpoint_aliases=endpoint_router(
                diagram_connections,
                alias_by_id=alias_by_id,
                alias_by_occurrence=occurrence_alias_by_id(occurrences),
            ),
        )
        if conn_lines:
            lines.append("' Connections")
            lines.extend(conn_lines)
            lines.append("")

        lines.append("@enduml")
        # Scale guard: hundreds of hidden layout chains (rows, grids, anchors) feed
        # GraphViz a constraint system it solves less and less reliably — at ad-hoc
        # viewpoint-preview scale it CRASHES outright. Past this size, readable
        # micro-layout is moot anyway: drop the chains, keep boxes/nesting/arrows,
        # and let the picture render.
        if len(render_entities) > 100:
            lines = [line for line in lines if "-[hidden]" not in line]
        body = "\n".join(lines)
        threshold = configured_puml_size_warning_threshold(self._config)
        warn_when_puml_exceeds_threshold(body, threshold=threshold)
        return body

    def inject_includes(self, body: str, repo_root: Path) -> str:
        declarations = ArchimateDeclarations.from_repo(repo_root)
        if declarations.are_inlined_in(body):
            # The body carries the expansion already. It gets restated, not marked: a marker here
            # would expand a second preamble beside the one that is there.
            return declarations.restated_in(body)
        _STEREO = "!include ../_archimate-stereotypes.puml"
        _GLYPH = "!include ../_archimate-glyphs.puml"
        for marker in (_STEREO, _GLYPH):
            if marker not in body:
                body = re.sub(r"(@startuml(?:\s+\S+)?)\n", rf"\1\n{marker}\n", body, count=1)
        return inject_archimate_includes(body, repo_root)


    def visible_connection_label(
        self,
        conn: ConnectionRecord,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> str:
        del diagram_connections
        return format_multiplicity_label(conn.src_multiplicity, conn.tgt_multiplicity)

    def _includes(self) -> list[str]:
        return [str(value) for value in self._config.get("includes", ())]

    def _connection_info(self, conn_type: str) -> ConnectionTypeInfo | None:
        return _registry().find_connection_type(ConnectionTypeName(conn_type))

    def _specialization_catalog(self) -> SpecializationCatalog:
        """The merged specialization catalog across every registered ontology — same
        module-registry-singleton pattern already used by `_connection_info`/
        `_junction_types` above, not a new service-locator surface."""
        return merge_specialization_catalogs(
            *(module.specialization_catalog for module in _registry().all_ontologies().values())
        )

    def _junction_types(self) -> frozenset[str]:
        return frozenset(_registry().entity_types_with_class(ElementClassName("junction")))

    def _classified_conn_types(self, config_key: str, default: str) -> frozenset[str]:
        layout = self._config.get("layout", {})
        if not isinstance(layout, dict):
            return frozenset()
        values = layout.get(config_key, [default])
        if not isinstance(values, list):
            return frozenset()
        result: set[str] = set()
        for value in values:
            result.update(_registry().connection_types_with_class(str(value)))
        return frozenset(result)

    def _nesting_conn_types(self) -> frozenset[str]:
        return self._classified_conn_types("nesting_connection_classes", "nesting")

    def _flow_conn_types(self) -> frozenset[str]:
        return self._classified_conn_types("flow_connection_classes", "dynamic")

    def _orders_upward(self, conn_type: str) -> bool:
        info = self._connection_info(conn_type)
        return info is not None and info.derivation_role == "structural"

    def _flow_through_entity_types(self) -> frozenset[str]:
        layout = self._config.get("layout", {})
        values: object = layout.get("flow_through_entity_types", []) if isinstance(layout, dict) else []
        return frozenset(str(value) for value in values) if isinstance(values, list) else frozenset()

    def _build_visual_nesting(
        self,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        alias_by_id: Mapping[str, str],
        entity_by_alias: Mapping[str, EntityRecord],
    ) -> tuple[dict[str, list[EntityRecord]], set[str]]:
        return build_generic_visual_nesting(
            entities=entities,
            connections=connections,
            alias_by_id=alias_by_id,
            entity_by_alias=entity_by_alias,
            nesting_connection_types=self._nesting_conn_types(),
            junction_entity_types=self._junction_types(),
            flow_through_entity_types=self._flow_through_entity_types(),
        )
