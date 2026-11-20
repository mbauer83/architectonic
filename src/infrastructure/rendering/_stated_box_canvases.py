"""The component canvas as a diagram that states its boxes uses it: once per ruled box, once for the rest.

A diagram stating no ruled grouping gets its boxes computed — a box per domain, a box per type the
canvas decides to gather. One that states a ruled grouping has said which boxes it has, so nothing
is boxed that no grouping says is: each ruled box lays its own members out with the canvas a domain
box uses, and whatever no grouping holds stands on the canvas unboxed.

Each canvas ranks its components from zero. Their ranks are kept apart here, in the order the
canvases are laid out, so an arrow between two boxes is hinted along the order the diagram states
them in rather than by two unrelated counts that happen to differ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering._component_canvas import never_boxed


@dataclass
class StatedBoxCanvases:
    """Lays out members through *canvas*, the diagram's component canvas with its shared inputs applied."""

    canvas: Callable[..., list[str]]
    #: The diagram's one rank map, which the connection lines read.
    group_index_by_alias: dict[str, int]
    _ranks_given: int = 0

    def in_box(self, members: list[EntityRecord], stereotype: str, indent: str, alias_namespace: str) -> list[str]:
        """The lines for *members* inside a ruled box."""
        own_ranks: dict[str, int] = {}
        lines = self.canvas(
            top_entities=members, grouping=stereotype, indent=indent, alias_namespace=alias_namespace,
            group_index_by_alias=own_ranks, type_boxing=never_boxed,
        )
        for alias, rank in own_ranks.items():
            self.group_index_by_alias[alias] = self._ranks_given + rank
        self._ranks_given += max(own_ranks.values(), default=-1) + 1
        return lines

    def unboxed(self, members: list[EntityRecord]) -> list[str]:
        """The lines for what no grouping holds, standing directly on the canvas."""
        return self.in_box(members, "", "", "")
