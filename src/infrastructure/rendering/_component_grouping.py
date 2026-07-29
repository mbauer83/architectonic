"""Top-level canvas grouping by connected component of the diagram's connection graph.

A diagram may contain several unrelated constellations; each is laid out as its own
unit, never interleaved with another. Within a component the reading structure
depends on what the component expresses:

* A component WITH flow reads as a SPINE with SATELLITES. The spine holds every
  chain link — an item with both incoming and outgoing flow, or one that visually
  nests children (a process box is a spine station even when the chain enters it
  through an event) — laid inline along the flow. Everything else is a satellite:
  pure sources sit before the spine, sinks and non-flow neighbours after, each
  side batched into labeled element-type boxes when two or more share a type
  (a request-events box feeding the spine, exactly how the hand-tuned diagrams
  read), a lone satellite standing bare.

* A component WITHOUT flow reads as TYPE LAYERS: one labeled box per element type,
  layers ordered by the direction of the connections between the types (drivers
  above the assessments they feed, goals above the outcomes realizing them),
  members spread along the reading axis inside their layer. This is the layered
  motivation/capability view.

* Elements with no connections at all fall back to plain type boxes (two or more
  of a type) or stand bare.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.application.modeling.flow_ordering import order_aliases_along_flow

RenderEntity = Callable[..., list[str]]


@dataclass(frozen=True)
class TopLevelComponents:
    """Connected components over the top-level aliases, plus the connectionless rest."""

    components: list[list[str]]  # each in the caller's original member order
    isolated: list[str]  # no incident edges at all — the only plain type-box candidates


def lift_edges_to_top(
    edges: list[tuple[str, str]],
    top_of: dict[str, str],
) -> list[tuple[str, str]]:
    """Rewrite alias edges onto the top-level items that visually contain them.

    Edges inside one top-level item (both endpoints under the same top) vanish —
    they order that item's children, not the canvas.
    """
    lifted: list[tuple[str, str]] = []
    for source_alias, target_alias in edges:
        top_source = top_of.get(source_alias)
        top_target = top_of.get(target_alias)
        if top_source and top_target and top_source != top_target:
            lifted.append((top_source, top_target))
    return lifted


def partition_top_level_components(
    top_aliases: list[str],
    lifted_edges: list[tuple[str, str]],
) -> TopLevelComponents:
    """Split *top_aliases* into connected components (stable order) and isolates."""
    neighbors: dict[str, set[str]] = defaultdict(set)
    alias_set = set(top_aliases)
    for source_alias, target_alias in lifted_edges:
        if source_alias in alias_set and target_alias in alias_set:
            neighbors[source_alias].add(target_alias)
            neighbors[target_alias].add(source_alias)

    position = {alias: index for index, alias in enumerate(top_aliases)}
    assigned: set[str] = set()
    components: list[list[str]] = []
    isolated: list[str] = []
    for alias in top_aliases:
        if alias in assigned:
            continue
        if not neighbors.get(alias):
            isolated.append(alias)
            assigned.add(alias)
            continue
        stack = [alias]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in members:
                continue
            members.add(current)
            stack.extend(neighbor for neighbor in neighbors.get(current, ()) if neighbor not in members)
        components.append(sorted(members, key=lambda member: position[member]))
        assigned.update(members)
    return TopLevelComponents(components=components, isolated=isolated)


@dataclass(frozen=True)
class SpinePartition:
    """One flow component split into its inline spine and its satellite fringe."""

    spine: list[str]  # flow order
    sources: list[str]  # only outgoing flow — placed before the spine
    trailing: list[str]  # sinks and non-flow neighbours — placed after the spine


def split_spine_and_satellites(
    component_members: list[str],
    *,
    flow_edges_in_component: list[tuple[str, str]],
    has_children: Callable[[str], bool],
) -> SpinePartition:
    """Chain links and nest parents form the spine; the rest is fringe."""
    flow_in: dict[str, int] = defaultdict(int)
    flow_out: dict[str, int] = defaultdict(int)
    for source_alias, target_alias in flow_edges_in_component:
        flow_out[source_alias] += 1
        flow_in[target_alias] += 1

    spine_members = [
        alias
        for alias in component_members
        if (flow_in[alias] > 0 and flow_out[alias] > 0) or has_children(alias)
    ]
    if not spine_members:
        # Degenerate chain (a single hop has no middle link): every flow participant
        # IS the spine — batching them into type boxes would hide the flow.
        spine_members = [alias for alias in component_members if flow_in[alias] or flow_out[alias]]
    spine_set = set(spine_members)
    sources = [
        alias
        for alias in component_members
        if alias not in spine_set and flow_out[alias] > 0 and flow_in[alias] == 0
    ]
    trailing = [alias for alias in component_members if alias not in spine_set and alias not in set(sources)]
    ordered_spine = order_aliases_along_flow(aliases=spine_members, flow_edges=flow_edges_in_component)
    return SpinePartition(spine=ordered_spine, sources=sources, trailing=trailing)


def type_layer_order(
    members: list[str],
    directed_edges: list[tuple[str, str]],
    type_of: Callable[[str], str],
) -> list[str]:
    """Element types of *members*, ordered by the direction of cross-type edges.

    A type whose members' connections point at another type's members reads as the
    layer above it; cycles and untouched types keep first-appearance order."""
    type_sequence: list[str] = []
    for alias in members:
        if type_of(alias) not in type_sequence:
            type_sequence.append(type_of(alias))
    member_set = set(members)
    cross_type_edges = [
        (type_of(source_alias), type_of(target_alias))
        for source_alias, target_alias in directed_edges
        if source_alias in member_set
        and target_alias in member_set
        and type_of(source_alias) != type_of(target_alias)
    ]
    return order_aliases_along_flow(aliases=type_sequence, flow_edges=cross_type_edges)


def collect_subtree_aliases(entity: Any, children_map: Mapping[str, list[Any]]) -> set[str]:
    """Aliases of *entity* and every visually nested descendant."""
    from src.application.artifact_parsing import normalize_puml_alias  # noqa: PLC0415

    aliases: set[str] = set()
    stack = [entity]
    while stack:
        current = stack.pop()
        alias = normalize_puml_alias(current.display_alias)
        if alias:
            aliases.add(alias)
        stack.extend(children_map.get(alias, ()))
    return aliases
