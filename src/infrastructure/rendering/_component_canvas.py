"""Assemble the canvas lines for one domain's top-level items.

The structural decisions live in ``_component_grouping``; this module only walks
components in order and emits entities, type boxes and hidden layout chains.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.application.artifact_parsing import normalize_puml_alias
from src.application.modeling.flow_ordering import order_aliases_along_flow
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering._component_grouping import (
    RenderEntity,
    lift_edges_to_top,
    partition_top_level_components,
    split_spine_and_satellites,
    type_layer_order,
)
from src.infrastructure.rendering._diagram_layout import wrapped_grid_lines
from src.infrastructure.rendering.archimate_entity_declarations import ordered_entity_type_groups


class _CanvasEmitter:
    """Accumulates canvas lines with one running anchor chain down the page."""

    def __init__(
        self,
        *,
        entity_by_alias: dict[str, EntityRecord],
        render_entity: RenderEntity,
        group_index_by_alias: dict[str, int],
        grouping: str,
        registry: Any,
        indent: str,
        alias_namespace: str = "",
        connected_pairs: frozenset[frozenset[str]] = frozenset(),
    ) -> None:
        self.lines: list[str] = []
        self._entity_by_alias = entity_by_alias
        self._render_entity = render_entity
        self._group_index_by_alias = group_index_by_alias
        self._grouping = grouping
        self._registry = registry
        self._indent = indent
        self._alias_namespace = alias_namespace
        self._connected_pairs = connected_pairs
        self._prev_anchor: str | None = None
        self._prev_members: list[str] = []
        self._box_counter = 0
        self.group_index = 0

    def _chain_wrapped_unit(self, member_aliases: list[str], box_alias: str | None) -> None:
        handle = box_alias if box_alias else (member_aliases[-1] if member_aliases else None)
        if self._prev_anchor and handle and not self._units_connected(member_aliases):
            self.lines.append(f"{self._indent}{self._prev_anchor} -[hidden]down- {handle}")
        if handle:
            self._prev_anchor = handle
            self._prev_members = list(member_aliases)
        self.lines.append("")

    def _units_connected(self, members: list[str]) -> bool:
        return any(
            frozenset((prev, curr)) in self._connected_pairs
            for prev in self._prev_members
            for curr in members
        )

    def chain(self, ordered: list[str], *, axis: str = "down", handle: str | None = None) -> None:
        """Chain *ordered* along *axis*; anchor the UNIT to the previous one via its
        handle (the box alias when boxed). Hidden edges touching a box crash GraphViz
        shape-dependently, so the anchor is emitted ONLY between units no real arrow
        already connects — connected units rank via the arrows' direction hints."""
        for idx in range(len(ordered) - 1):
            self.lines.append(f"{self._indent}{ordered[idx]} -[hidden]{axis}- {ordered[idx + 1]}")
        unit_head = handle if handle is not None else (ordered[0] if ordered else None)
        unit_tail = handle if handle is not None else (ordered[-1] if ordered else None)
        if self._prev_anchor and unit_head and not self._units_connected(ordered):
            self.lines.append(f"{self._indent}{self._prev_anchor} -[hidden]down- {unit_head}")
        if unit_tail:
            self._prev_anchor = unit_tail
            self._prev_members = list(ordered)
        self.lines.append("")

    def emit_bare(self, ordered: list[str], *, axis: str = "down") -> None:
        for alias in ordered:
            self.lines.extend(self._render_entity(self._entity_by_alias[alias], self._indent, axis))
            self._group_index_by_alias[alias] = self.group_index
        self.chain(ordered, axis=axis)

    def emit_typed_batch(
        self,
        aliases: list[str],
        *,
        member_axis: str,
        box_singletons: bool,
        types_elsewhere: frozenset[str] = frozenset(),
    ) -> None:
        """Element-type boxes for *aliases*; singleton types stand bare unless asked.

        A type that ALSO occurs un-boxed elsewhere in the same component never gets a
        box — a "Functions" box next to a bare function reads as a false partition."""
        entities = [self._entity_by_alias[alias] for alias in aliases]
        for label, grouped in ordered_entity_type_groups(entities, self._registry):
            if grouped and grouped[0].artifact_type in types_elsewhere:
                self.emit_bare(
                    [a for e in grouped if (a := normalize_puml_alias(e.display_alias))], axis=member_axis
                )
                continue
            self._emit_type_box(label, grouped, member_axis=member_axis, box_singletons=box_singletons)

    def emit_type_layer(self, label: str, grouped: list[EntityRecord], *, box_singletons: bool) -> None:
        self._emit_type_box(label, grouped, member_axis="right", box_singletons=box_singletons)

    def _emit_type_box(
        self, label: str, grouped: list[EntityRecord], *, member_axis: str, box_singletons: bool
    ) -> None:
        boxed = len(grouped) > 1 or box_singletons
        box_alias: str | None = None
        if boxed:
            self._box_counter += 1
            box_alias = f"GRPT_{self._alias_namespace}{self._box_counter}"
            self.lines.append(f'{self._indent}rectangle "{label}" <<{self._grouping}>> as {box_alias} {{')
        member_aliases: list[str] = []
        for entity in grouped:
            self.lines.extend(
                self._render_entity(entity, self._indent + ("  " if boxed else ""), member_axis)
            )
            alias = normalize_puml_alias(entity.display_alias)
            if alias:
                self._group_index_by_alias[alias] = self.group_index
                member_aliases.append(alias)
        if boxed:
            self.lines.append(f"{self._indent}}}")
        if len(member_aliases) > 4:
            # Wrap large member sets into a grid — one long line sacrifices compactness.
            cross = "down" if member_axis == "right" else "right"
            self.lines.extend(
                wrapped_grid_lines(
                    member_aliases, main_axis=member_axis, cross_axis=cross, indent=self._indent
                )
            )
            self._chain_wrapped_unit(member_aliases, box_alias)
        else:
            self.chain(member_aliases, axis=member_axis, handle=box_alias)


def render_component_canvas(
    *,
    top_entities: list[EntityRecord],
    connections: Sequence[ConnectionRecord],
    alias_by_id: Mapping[str, str],
    children_map: Mapping[str, list[EntityRecord]],
    flow_edges: list[tuple[str, str]],
    render_entity: RenderEntity,
    group_index_by_alias: dict[str, int],
    grouping: str,
    nesting_conn_types: frozenset[str],
    registry: Any,
    indent: str = "",
    alias_namespace: str = "",
    orders_upward: Any = None,
) -> list[str]:
    """One canvas unit per connected component; see ``_component_grouping`` for the rules."""
    top_aliases = [alias for entity in top_entities if (alias := normalize_puml_alias(entity.display_alias))]
    entity_by_top_alias = {
        normalize_puml_alias(entity.display_alias): entity for entity in top_entities if entity.display_alias
    }

    top_of: dict[str, str] = {}

    def _assign_top(top_alias: str, alias: str) -> None:
        top_of[alias] = top_alias
        for child in children_map.get(alias, ()):
            child_alias = normalize_puml_alias(child.display_alias)
            if child_alias:
                _assign_top(top_alias, child_alias)

    for alias in top_aliases:
        _assign_top(alias, alias)

    all_pairs: list[tuple[str, str]] = []
    directed_pairs: list[tuple[str, str]] = []
    for conn in connections:
        src = alias_by_id.get(conn.source)
        tgt = alias_by_id.get(conn.target)
        if not src or not tgt:
            continue
        all_pairs.append((src, tgt))
        if conn.conn_type not in nesting_conn_types:
            # Constitution-style relations (realization, assignment — ontology
            # derivation role "structural") read UPWARD: the realizer belongs
            # below what it realizes. Invert them for ORDERING only; the drawn
            # arrow still points up via the layer-rank direction hint.
            if orders_upward is not None and orders_upward(conn.conn_type):
                directed_pairs.append((tgt, src))
            else:
                directed_pairs.append((src, tgt))
    lifted_all = lift_edges_to_top(all_pairs, top_of)
    lifted_flow = lift_edges_to_top(flow_edges, top_of)
    lifted_directed = lift_edges_to_top(directed_pairs, top_of)

    parts = partition_top_level_components(top_aliases, lifted_all)
    connected_pairs = frozenset(frozenset(pair) for pair in lifted_all if pair[0] != pair[1])
    emitter = _CanvasEmitter(
        entity_by_alias=entity_by_top_alias,
        render_entity=render_entity,
        group_index_by_alias=group_index_by_alias,
        grouping=grouping,
        registry=registry,
        indent=indent,
        alias_namespace=alias_namespace,
        connected_pairs=connected_pairs,
    )

    def _type_of(alias: str) -> str:
        return entity_by_top_alias[alias].artifact_type

    layered_members: list[str] = []
    for component in parts.components:
        member_set = set(component)
        flow_in_component = [
            (source_alias, target_alias)
            for source_alias, target_alias in lifted_flow
            if source_alias in member_set and target_alias in member_set
        ]
        if not flow_in_component:
            # Flowless components merge into ONE layered view: two unlabeled
            # "Resources" boxes distinguish nothing — a shared layer reads better.
            layered_members.extend(component)
            continue
        if flow_in_component:
            partition = split_spine_and_satellites(
                component,
                flow_edges_in_component=flow_in_component,
                has_children=lambda alias: bool(children_map.get(alias)),
            )
            spine_types = frozenset(_type_of(alias) for alias in partition.spine)
            emitter.emit_typed_batch(
                partition.sources, member_axis="right", box_singletons=False, types_elsewhere=spine_types
            )
            emitter.emit_bare(partition.spine)
            emitter.emit_typed_batch(
                partition.trailing, member_axis="right", box_singletons=False, types_elsewhere=spine_types
            )
        emitter.group_index += 1

    if layered_members:
        member_set = set(layered_members)
        directed_in_layers = [
            (source_alias, target_alias)
            for source_alias, target_alias in lifted_directed
            if source_alias in member_set and target_alias in member_set
        ]
        layer_types = type_layer_order(layered_members, directed_in_layers, _type_of)
        if len(layer_types) < 2:
            # One type only: layers would say nothing — order along the edges instead.
            ordered = order_aliases_along_flow(aliases=layered_members, flow_edges=directed_in_layers)
            emitter.emit_bare(ordered)
            emitter.group_index += 1
        else:
            grouped_by_label = {
                label: grouped
                for label, grouped in ordered_entity_type_groups(
                    [entity_by_top_alias[alias] for alias in layered_members], registry
                )
            }
            label_by_type = {
                grouped[0].artifact_type: label for label, grouped in grouped_by_label.items() if grouped
            }
            for layer_type in layer_types:
                label = label_by_type.get(layer_type, layer_type.title())
                emitter.emit_type_layer(label, grouped_by_label.get(label, []), box_singletons=False)
                # Every layer ranks on its own so cross-layer arrows keep the
                # declared reading order even when a minority edge points against it.
                emitter.group_index += 1

    if parts.isolated:
        emitter.emit_typed_batch(parts.isolated, member_axis="down", box_singletons=False)
        emitter.group_index += 1
    return emitter.lines
