"""Which declared step edges the renderer's index can hold only one of.

About the **index**, not the graph — it takes connections and no `StepGraph` at all, which is why it
is not in `_step_graph`. `_build_single_target` is a dict comprehension keyed by `source`, so a second
edge of one type out of one step is discarded when the index is built, before any walk runs. Nothing
reported that: W045 asks whether every declared *step* is drawn and there was no equivalent for an
edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Edge types the renderer indexes **single-target**, keyed by the step the edge leaves.
#:
#: `step-fork-branch` is deliberately absent: it is the one type built with `_build_multi_target`, so
#: a fork may declare as many branches as it likes and none is lost. Naming the safe type by its
#: absence is what keeps this list honest — it is a statement about the index, not a guess.
SINGLE_TARGET_BY_SOURCE: tuple[str, ...] = (
    "step-flow",
    "step-then",
    "step-else",
    "step-contains",
    "step-in-lane",
)

#: Edge types indexed single-target keyed by the step the edge arrives at, not the one it leaves.
#:
#: One type, and it is the same accident with the opposite key: two notes on one step lose one, where
#: two flows out of one step lose one. Lumping the two keys together would report the wrong collision
#: for whichever half it chose.
SINGLE_TARGET_BY_TARGET: tuple[str, ...] = ("step-note-of",)


@dataclass(frozen=True)
class CollidingDeclaration:
    """Declared edges of one type that the index can hold only one of.

    `kept` is what the index ends up with, which is the *last* one declared — a dict comprehension
    keeps the final assignment. Naming it lets a diagnostic say which edge survived rather than only
    that several did not, so an author can tell whether the survivor is the one they meant.
    """

    conn_type: str
    #: The step the collision is keyed on: the source for most types, the target for a note.
    keyed_on: str
    #: Every edge declared under that key, in declaration order, as `(source, target)`.
    edges: tuple[tuple[str, str], ...]

    @property
    def kept(self) -> tuple[str, str]:
        return self.edges[-1]

    @property
    def lost(self) -> tuple[tuple[str, str], ...]:
        return self.edges[:-1]


def colliding_declarations(connections: Sequence[Mapping[str, Any]]) -> tuple[CollidingDeclaration, ...]:
    """Declared edges the renderer's index cannot all hold.

    A grouping over declared data — no traversal, no graph, no body. That is what makes it **complete
    by construction**: every edge of a single-target type is either alone under its key or not, and
    there is no third case for an enumeration to miss. An earlier design recorded the edges a *walk*
    skipped and could never be complete, because the reasons a walk skips one are open-ended.

    Ordered by type then key so a diagram reports the same collisions in the same order every time.
    """
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for item in connections:
        conn_type = str(item.get("conn_type") or "")
        source, target = str(item.get("source") or ""), str(item.get("target") or "")
        if not source or not target:
            continue
        if conn_type in SINGLE_TARGET_BY_SOURCE:
            grouped.setdefault((conn_type, source), []).append((source, target))
        elif conn_type in SINGLE_TARGET_BY_TARGET:
            grouped.setdefault((conn_type, target), []).append((source, target))
    return tuple(
        CollidingDeclaration(conn_type=conn_type, keyed_on=key, edges=tuple(edges))
        for (conn_type, key), edges in sorted(grouped.items())
        if len(edges) > 1
    )
