"""The declared step graph, and where a set of branches converges.

The renderer builds this from `diagram_connections`; `_emission` walks it. Kept apart from the walk
because the questions are different in kind: this module answers "where can control go from here"
and "where do these branches meet", with no notion of a line of PlantUML.

**Convergence is post-dominance, not reachability**, and the distinction is the whole of defect 9's
third cause. A step both arms of a decision *can* reach may still be escaped by a path through one
of them; hoisting it past the `endif` would then draw it on a path that never had it. So a
convergence point is a step every branch reaches **and** that no path out of the branching step
gets past — which is exactly what makes drawing it once, after the construct, faithful.

A step reached from several branches that is *not* a convergence point is the residue: the arrivals
sit at different nesting depths and no single structured placement covers them. `_emission` draws
those with a connector pair.

**It also owns which declared edges a body can carry at all**, which is a different question from
where control goes. The renderer indexes most edge types single-target — a dict keyed by `source` —
so a second edge of one type out of one step is discarded when the index is built, before any walk
runs. Nothing reported that: W045 asks whether every declared *step* is drawn and there was no
equivalent for an edge. `colliding_declarations` is that answer, and it is here rather than in the
contribution because the rule is about the declared graph, not about a picture.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StepGraph:
    """Which steps the diagram declares, and where control goes from each of them."""

    step_by_id: Mapping[str, dict[str, Any]]
    flow_next: Mapping[str, str]
    then_target: Mapping[str, str]
    else_target: Mapping[str, str]
    fork_branches: Mapping[str, Sequence[str]]
    contains_first: Mapping[str, str]

    def kind_of(self, step_id: str) -> str:
        step = self.step_by_id.get(step_id)
        return str(step.get("type") or "") if step else ""

    def arms_of(self, step_id: str) -> tuple[str, ...]:
        """The branches this step opens: a decision's two arms, or a fork's branches."""
        kind = self.kind_of(step_id)
        if kind == "decision":
            return tuple(
                target for target in (self.then_target.get(step_id), self.else_target.get(step_id))
                if target
            )
        if kind == "fork":
            return tuple(self.fork_branches.get(step_id) or ())
        return ()

    def successors_of(self, step_id: str) -> tuple[str, ...]:
        """Where control can go from *step_id*.

        A decision's declared merge edge is deliberately not a successor of the decision: the arms
        fall through to it, so counting it here would offer a path around both arms.
        """
        arms = self.arms_of(step_id)
        if arms:
            return arms
        onward = self.flow_next.get(step_id)
        if self.kind_of(step_id) == "partition":
            contained = self.contains_first.get(step_id)
            return tuple(target for target in (contained, onward) if target)
        return (onward,) if onward else ()

    def reachable_from(self, start: str) -> frozenset[str]:
        seen: set[str] = set()
        pending = [start]
        while pending:
            step_id = pending.pop()
            if step_id in seen:
                continue
            seen.add(step_id)
            pending.extend(self.successors_of(step_id))
        return frozenset(seen)

    def _escapes(self, start: str, without: str) -> bool:
        """Can control leave *start* and run out of graph without ever passing *without*?"""
        seen: set[str] = set()
        pending = [start]
        while pending:
            step_id = pending.pop()
            if step_id == without or step_id in seen:
                continue
            seen.add(step_id)
            successors = self.successors_of(step_id)
            if not successors:
                return True
            pending.extend(successors)
        return False

    def convergence_point(self, step_id: str) -> str | None:
        """The first step every branch of *step_id* reaches and no path out of it escapes.

        None where the step opens fewer than two branches, or where the arrivals are at different
        nesting depths — the residue `goto` exists for.
        """
        arms = self.arms_of(step_id)
        if len(arms) < 2:
            return None
        common: frozenset[str] = frozenset.intersection(
            *(self.reachable_from(arm) for arm in arms)
        ) - {step_id}
        dominating = sorted(c for c in common if not self._escapes(step_id, without=c))
        for candidate in dominating:
            onward = self.reachable_from(candidate) - {candidate}
            if all(other in onward for other in dominating if other != candidate):
                return candidate
        return None


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
