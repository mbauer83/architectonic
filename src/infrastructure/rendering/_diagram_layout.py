from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from src.application.modeling.flow_ordering import order_aliases_along_flow


def _pairwise(items: list[str]) -> list[tuple[str, str]]:
    return list(zip(items, items[1:], strict=False))


def _filtered_neighbors(
    neighbors: set[str] | tuple[str, ...],
    allowed_aliases: set[str],
    key: Callable[[str], int],
) -> list[str]:
    return sorted((alias for alias in neighbors if alias in allowed_aliases), key=key)


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
