from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TypeVar

from src.application.modeling.flow_ordering import order_aliases_along_flow

T = TypeVar("T")


def _pairwise(items: list[str]) -> list[tuple[str, str]]:
    return list(zip(items, items[1:], strict=False))


def _filtered_neighbors(
    neighbors: set[str] | tuple[str, ...],
    allowed_aliases: set[str],
    key: Callable[[str], int],
) -> list[str]:
    return sorted((alias for alias in neighbors if alias in allowed_aliases), key=key)


def _collect_junction_component(
    start_alias: str,
    *,
    junction_aliases: set[str],
    junction_neighbors: dict[str, set[str]],
    visited: set[str],
) -> tuple[list[str], set[str]]:
    component: list[str] = []
    endpoint_aliases: set[str] = set()
    stack = [start_alias]
    while stack:
        current = stack.pop()
        if current not in visited:
            visited.add(current)
            component.append(current)
            neighbor_aliases = junction_neighbors.get(current, ())
            stack.extend(
                neighbor_alias
                for neighbor_alias in neighbor_aliases
                if neighbor_alias in junction_aliases and neighbor_alias not in visited
            )
            endpoint_aliases.update(
                neighbor_alias for neighbor_alias in neighbor_aliases if neighbor_alias not in junction_aliases
            )
    return component, endpoint_aliases


def _nest_component_items(
    *,
    parent_alias: str,
    component_aliases: list[str],
    item_by_alias: dict[str, T],
    children_map: dict[str, list[T]],
    nested_aliases: set[str],
) -> None:
    nested_items = [
        item_by_alias[component_alias]
        for component_alias in component_aliases
        if component_alias not in nested_aliases and component_alias in item_by_alias
    ]
    children_map[parent_alias].extend(nested_items)
    nested_aliases.update(
        component_alias
        for component_alias in component_aliases
        if component_alias in item_by_alias and component_alias not in nested_aliases
    )


def _add_branch_layout_lines(
    *,
    anchor_alias: str,
    related_aliases: list[str],
    line_template: str,
    extra_lines: list[str],
    pair_axis_overrides: dict[tuple[str, str], str],
    branch_axis: str,
) -> None:
    if len(related_aliases) < 2:
        return
    extra_lines.extend(
        line_template.format(anchor=anchor_alias, related=related_alias)
        for related_alias in related_aliases
    )
    pair_axis_overrides.update({pair: branch_axis for pair in _pairwise(related_aliases)})


def _branch_hint_pairs(group: list[str], branch_axis: str) -> dict[tuple[str, str], str]:
    direction_pairs = [
        ((left_alias, right_alias), (right_alias, left_alias))
        for left_index, left_alias in enumerate(group)
        for right_alias in group[left_index + 1 :]
    ]
    if branch_axis == "right":
        return {
            pair: direction
            for pair_group, directions in ((pairs, ("right", "left")) for pairs in direction_pairs)
            for pair, direction in zip(pair_group, directions, strict=True)
        }
    return {
        pair: direction
        for pair_group, directions in ((pairs, ("down", "up")) for pairs in direction_pairs)
        for pair, direction in zip(pair_group, directions, strict=True)
    }


def select_deepest_common_parent(
    endpoint_aliases: set[str],
    direct_parent_by_alias: dict[str, str],
) -> str | None:
    if not endpoint_aliases:
        return None

    chains_by_alias: dict[str, list[str]] = {}
    for alias in endpoint_aliases:
        chain: list[str] = []
        current = alias
        while parent := direct_parent_by_alias.get(current):
            chain.append(parent)
            current = parent
        if not chain:
            return None
        chains_by_alias[alias] = chain

    common = set(chains_by_alias[next(iter(chains_by_alias))])
    for chain in chains_by_alias.values():
        common &= set(chain)
    if not common:
        return None

    def _distance(alias: str, parent_alias: str) -> int:
        return chains_by_alias[alias].index(parent_alias)

    return min(
        common,
        key=lambda parent_alias: (
            max(_distance(alias, parent_alias) for alias in chains_by_alias),
            sum(_distance(alias, parent_alias) for alias in chains_by_alias),
            parent_alias,
        ),
    )


def build_visual_nesting(
    *,
    item_by_alias: dict[str, T],
    structural_edges: list[tuple[str, str]],
    neighbor_edges: list[tuple[str, str]],
    junction_aliases: set[str],
    flow_through_aliases: set[str] | None = None,
) -> tuple[dict[str, list[T]], set[str]]:
    children_map: dict[str, list[T]] = defaultdict(list)
    direct_parent_by_alias: dict[str, str] = {}
    nested_aliases: set[str] = set()
    junction_neighbors: dict[str, set[str]] = defaultdict(set)

    for source_alias, target_alias in structural_edges:
        if target_alias in item_by_alias:
            children_map[source_alias].append(item_by_alias[target_alias])
            direct_parent_by_alias[target_alias] = source_alias
            nested_aliases.add(target_alias)

    for source_alias, target_alias in neighbor_edges:
        if source_alias in junction_aliases:
            junction_neighbors[source_alias].add(target_alias)
        if target_alias in junction_aliases:
            junction_neighbors[target_alias].add(source_alias)

    visited: set[str] = set()
    for junction_alias in sorted(junction_aliases):
        if junction_alias not in visited and junction_alias not in direct_parent_by_alias:
            component, endpoint_aliases = _collect_junction_component(
                junction_alias,
                junction_aliases=junction_aliases,
                junction_neighbors=junction_neighbors,
                visited=visited,
            )
            if parent_alias := select_deepest_common_parent(endpoint_aliases, direct_parent_by_alias):
                _nest_component_items(
                    parent_alias=parent_alias,
                    component_aliases=component,
                    item_by_alias=item_by_alias,
                    children_map=children_map,
                    nested_aliases=nested_aliases,
                )

    # A flow-through element (an event, per the diagram type's declaration) that sits
    # BETWEEN members of one container — every predecessor and successor already nested
    # under a common parent — is part of the sequence that container orchestrates, and
    # nests there too. One-sided attachments (a pure source or sink) stay outside.
    for alias in sorted(flow_through_aliases or ()):
        if alias in nested_aliases or alias in junction_aliases or alias not in item_by_alias:
            continue
        incoming = {source for source, target in neighbor_edges if target == alias}
        outgoing = {target for source, target in neighbor_edges if source == alias}
        if not incoming or not outgoing:
            continue
        parent_alias = select_deepest_common_parent(incoming | outgoing, direct_parent_by_alias)
        if parent_alias:
            children_map[parent_alias].append(item_by_alias[alias])
            direct_parent_by_alias[alias] = parent_alias
            nested_aliases.add(alias)

    return children_map, nested_aliases


def wrapped_grid_lines(
    aliases: list[str],
    *,
    main_axis: str,
    cross_axis: str,
    indent: str,
    width: int = 4,
) -> list[str]:
    """Hidden chains arranging *aliases* as a grid: rows of *width* along the main
    axis, rows stacked along the cross axis — many members without flow order would
    otherwise stretch a single line and sacrifice compactness."""
    rows = [aliases[start : start + width] for start in range(0, len(aliases), width)]
    lines: list[str] = []
    for row in rows:
        for idx in range(len(row) - 1):
            lines.append(f"{indent}{row[idx]} -[hidden]{main_axis}- {row[idx + 1]}")
    for idx in range(len(rows) - 1):
        lines.append(f"{indent}{rows[idx][0]} -[hidden]{cross_axis}- {rows[idx + 1][0]}")
    return lines


def build_nested_layout_lines(
    *,
    child_aliases: list[str],
    flow_edges: list[tuple[str, str]],
    junction_aliases: set[str],
    main_axis: str,
    branch_axis: str,
    indent: str,
) -> list[str]:
    if len(child_aliases) < 2:
        return []

    child_alias_set = set(child_aliases)
    if len(child_aliases) > 4 and not any(
        src in child_alias_set and tgt in child_alias_set for src, tgt in flow_edges
    ):
        # No flow orders these members — wrap them into a compact grid instead of
        # one long line along the main axis.
        return wrapped_grid_lines(
            child_aliases, main_axis=main_axis, cross_axis=branch_axis, indent=indent
        )

    # Restricted to the group's own members: a branch is drawn between siblings, so a junction's
    # successors outside the group are not part of this chain even though they position it.
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for src_alias, tgt_alias in flow_edges:
        if src_alias in child_alias_set and tgt_alias in child_alias_set:
            outgoing[src_alias].add(tgt_alias)
            incoming[tgt_alias].add(src_alias)

    ordered_aliases = order_aliases_along_flow(aliases=child_aliases, flow_edges=flow_edges)
    order_index = {alias: index for index, alias in enumerate(ordered_aliases)}

    def _ordered_position(alias: str) -> int:
        return order_index.get(alias, len(order_index))

    pair_axis_overrides: dict[tuple[str, str], str] = {}
    extra_lines: list[str] = []
    for junction_alias in ordered_aliases:
        if junction_alias in junction_aliases:
            successors = _filtered_neighbors(outgoing.get(junction_alias, ()), child_alias_set, _ordered_position)
            _add_branch_layout_lines(
                anchor_alias=junction_alias,
                related_aliases=successors,
                line_template=f"{indent}{{anchor}} -[hidden]{main_axis}- {{related}}",
                extra_lines=extra_lines,
                pair_axis_overrides=pair_axis_overrides,
                branch_axis=branch_axis,
            )
            predecessors = _filtered_neighbors(incoming.get(junction_alias, ()), child_alias_set, _ordered_position)
            _add_branch_layout_lines(
                anchor_alias=junction_alias,
                related_aliases=predecessors,
                line_template=f"{indent}{{related}} -[hidden]{main_axis}- {{anchor}}",
                extra_lines=extra_lines,
                pair_axis_overrides=pair_axis_overrides,
                branch_axis=branch_axis,
            )

    lines: list[str] = []
    for index in range(len(ordered_aliases) - 1):
        left = ordered_aliases[index]
        right = ordered_aliases[index + 1]
        axis = pair_axis_overrides.get((left, right), main_axis)
        lines.append(f"{indent}{left} -[hidden]{axis}- {right}")
    return [*lines, *extra_lines]


def build_branch_direction_hints(
    *,
    child_aliases: list[str],
    flow_edges: list[tuple[str, str]],
    junction_aliases: set[str],
    branch_axis: str,
) -> dict[tuple[str, str], str]:
    if len(child_aliases) < 2:
        return {}

    child_alias_set = set(child_aliases)
    original_index = {alias: index for index, alias in enumerate(child_aliases)}

    def _original_position(alias: str) -> int:
        return original_index.get(alias, len(original_index))

    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for src_alias, tgt_alias in flow_edges:
        if src_alias in child_alias_set and tgt_alias in child_alias_set:
            outgoing[src_alias].add(tgt_alias)
            incoming[tgt_alias].add(src_alias)

    hints: dict[tuple[str, str], str] = {}
    for junction_alias in child_aliases:
        if junction_alias in junction_aliases:
            successor_group = _filtered_neighbors(
                outgoing.get(junction_alias, ()),
                child_alias_set,
                _original_position,
            )
            predecessor_group = _filtered_neighbors(
                incoming.get(junction_alias, ()),
                child_alias_set,
                _original_position,
            )
            for group in (successor_group, predecessor_group):
                hints.update(_branch_hint_pairs(group, branch_axis))
    return hints
