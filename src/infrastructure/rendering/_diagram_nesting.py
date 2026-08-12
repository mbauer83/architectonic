"""Which elements are drawn INSIDE which — the containment graph resolved to a drawable forest.

Separate from ``_diagram_layout``, which arranges what this module has already decided to draw:
that one emits hidden chains and direction hints between siblings, this one answers who the
siblings are. They share no helper, and keeping both in one file put it past the size limit.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


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


@dataclass
class _NestingForest(Generic[T]):
    """The visual nesting as it is built, holding the invariant the picture depends on: a forest.

    PlantUML containment is a tree. A second `as ALIAS` for an alias already declared is read as a
    *reference* to the element already created, so the second container renders **empty** and that
    containment leaves the picture — with no error, a body that still parses, and every id in it
    still resolving, which is why such a body verified clean. Two shapes this model produces
    routinely are not trees: an element aggregated by two parents (measured: 29 declarations for 19
    aliases on one 17-element view, four boxes empty), and a containment cycle between two
    containers, which nested *every* element and so declared none — an empty diagram.

    A containment that cannot be nested is not dropped. It is simply absent from
    ``children_by_alias``, and ``render_connection_lines`` already draws exactly those as their own
    typed arrow: the relation keeps its ArchiMate notation instead of a box PlantUML discards.

    Parent, children and nested-ness are three views of ONE fact and are answered from one record,
    because as three records they drifted: children held every parent, the parent map held the
    last, and the junction path updated two of the three.
    """

    item_by_alias: Mapping[str, T]
    children_by_alias: dict[str, list[T]] = field(default_factory=lambda: defaultdict(list))
    parent_by_alias: dict[str, str] = field(default_factory=dict)

    @property
    def nested_aliases(self) -> set[str]:
        """Every alias drawn inside another — exactly those that have a parent."""
        return set(self.parent_by_alias)

    def nest(self, *, parent_alias: str, child_alias: str) -> None:
        """Draw *child_alias* inside *parent_alias*, where that keeps the nesting a forest."""
        if child_alias in self.item_by_alias and self._may_nest(parent_alias, child_alias):
            self.children_by_alias[parent_alias].append(self.item_by_alias[child_alias])
            self.parent_by_alias[child_alias] = parent_alias

    def _may_nest(self, parent_alias: str, child_alias: str) -> bool:
        return (
            parent_alias != child_alias
            # One parent per child, and the FIRST wins: that is the one PlantUML honours today,
            # so the picture keeps the box it already drew and gains the arrows it had lost.
            and child_alias not in self.parent_by_alias
            and child_alias not in self._ancestors_of(parent_alias)
        )

    def _ancestors_of(self, alias: str) -> Iterator[str]:
        """The chain of containers *alias* sits in, outermost last. Terminates because the
        invariant this class maintains admits no cycle."""
        current = alias
        while parent_alias := self.parent_by_alias.get(current):
            yield parent_alias
            current = parent_alias


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
    """The children each container draws, and every alias drawn inside another.

    Structural edges are proposals, not instructions: each is honoured where it keeps the drawing a
    forest, and the rest stay relations for the connection renderer to draw as arrows.
    """
    nesting: _NestingForest[T] = _NestingForest(item_by_alias=item_by_alias)
    junction_neighbors: dict[str, set[str]] = defaultdict(set)

    for source_alias, target_alias in structural_edges:
        nesting.nest(parent_alias=source_alias, child_alias=target_alias)

    for source_alias, target_alias in neighbor_edges:
        if source_alias in junction_aliases:
            junction_neighbors[source_alias].add(target_alias)
        if target_alias in junction_aliases:
            junction_neighbors[target_alias].add(source_alias)

    visited: set[str] = set()
    for junction_alias in sorted(junction_aliases):
        if junction_alias not in visited and junction_alias not in nesting.parent_by_alias:
            component, endpoint_aliases = _collect_junction_component(
                junction_alias,
                junction_aliases=junction_aliases,
                junction_neighbors=junction_neighbors,
                visited=visited,
            )
            if parent_alias := select_deepest_common_parent(endpoint_aliases, nesting.parent_by_alias):
                for component_alias in component:
                    nesting.nest(parent_alias=parent_alias, child_alias=component_alias)

    # A flow-through element (an event, per the diagram type's declaration) that sits
    # BETWEEN members of one container — every predecessor and successor already nested
    # under a common parent — is part of the sequence that container orchestrates, and
    # nests there too. One-sided attachments (a pure source or sink) stay outside.
    for alias in sorted(flow_through_aliases or ()):
        if alias in nesting.parent_by_alias or alias in junction_aliases or alias not in item_by_alias:
            continue
        incoming = {source for source, target in neighbor_edges if target == alias}
        outgoing = {target for source, target in neighbor_edges if source == alias}
        if not incoming or not outgoing:
            continue
        if parent_alias := select_deepest_common_parent(incoming | outgoing, nesting.parent_by_alias):
            nesting.nest(parent_alias=parent_alias, child_alias=alias)

    return nesting.children_by_alias, nesting.nested_aliases
