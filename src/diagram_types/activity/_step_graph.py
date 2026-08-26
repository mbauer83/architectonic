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

**Two questions about a graph live beside it, not in it.** `_step_cycles` asks which cycles it carries
and whether a `repeat` can draw each; `_edge_collisions` asks which declared edges the renderer's
index can hold, which is about the index rather than the graph and takes no graph at all. All three
were one module until it reached 311 counted lines against a 250 soft limit, with three concerns and
one name.
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
