"""A diagram's stated layout together with what joins it to a picture of that diagram.

A layout is keyed by the identities the diagram uses — instance ids, grouping ids, relation keys — and
a rendered picture knows only aliases. `LaidOutDiagram` is the layout with those joins already made,
by whoever holds the diagram's frontmatter, so that what draws the picture needs nothing but this
value and the picture: no repository, no frontmatter, no second reading of either.

Everything a picture names is named here by alias. An instance, a relation's end or a grouping's
member whose alias the diagram's own statements do not tell is simply absent, and what draws the
picture treats absence as not knowing — it leaves that shape where the renderer put it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from src.domain.diagrams.layout.layout_block import Layout


@dataclass(frozen=True)
class StatedGrouping:
    """One grouping the diagram states, as far as finding its box on a picture needs."""

    grouping_id: str
    #: The aliases of the members that settled in it directly, not in a subgroup.
    members: tuple[str, ...]
    groups: tuple[StatedGrouping, ...] = ()

    def every_grouping(self) -> Iterator[StatedGrouping]:
        yield self
        for group in self.groups:
            yield from group.every_grouping()


@dataclass(frozen=True)
class DrawnKind:
    """What the ontology says of one drawn element, as far as a grouping's rule asks: its domain and its type."""

    domain: str
    element_type: str


@dataclass(frozen=True)
class LaidOutDiagram:
    """A layout, and how each thing it names is called on a picture of its diagram."""

    layout: Layout
    #: The instance — an entity, or one further occurrence of one — drawn under each alias.
    instance_by_alias: Mapping[str, str]
    #: Every relation the diagram draws, by key, with the aliases of its source and its target.
    relations: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    groupings: tuple[StatedGrouping, ...] = ()
    #: What each drawn element is, by alias, where the diagram's own statements tell.
    kinds: Mapping[str, DrawnKind] = field(default_factory=dict)
    #: Whether the diagram's boxes for a domain and for a type are computed, and so addressed by rule.
    #: False once the diagram states a ruled grouping: every box it draws is then one it states.
    boxes_are_computed: bool = True

    def every_grouping(self) -> Iterator[StatedGrouping]:
        for grouping in self.groupings:
            yield from grouping.every_grouping()
