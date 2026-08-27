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

    def successors_including_merge(self, step_id: str) -> tuple[str, ...]:
        """Everywhere control can end up from *step_id*, a decision's merge edge included.

        **The other half of `successors_of`, and the distinction is load-bearing.** That one omits a
        decision's declared merge edge on purpose: the arms fall through to it, so offering it as a
        successor would give the walk a path *around* both arms, and that omission is what makes
        convergence work. It must stay.

        But reachability is a different question, and asking it with the walk's answer made any cycle
        whose path runs through a decision invisible — not drawn and not refused, with the picture
        asserting the flow runs straight through. On a retry loop holding one decision the walk's
        successors are literally `fix: (), skip: ()`: dead ends, so nothing reached the condition.

        So the walk asks `successors_of` and the cycle finder asks this. Two questions, one rule about
        what a merge edge is, in one place.
        """
        onward = list(self.successors_of(step_id))
        if self.kind_of(step_id) == "decision":
            merge = self.flow_next.get(step_id)
            if merge and merge not in onward:
                onward.append(merge)
        return tuple(onward)

    def reachable_including_merge(self, start: str) -> frozenset[str]:
        """Every step reachable from *start* when a decision's merge edge counts as a successor."""
        seen: set[str] = set()
        pending = [start]
        while pending:
            step_id = pending.pop()
            if step_id in seen:
                continue
            seen.add(step_id)
            pending.extend(self.successors_including_merge(step_id))
        return frozenset(seen)

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


#: The `diagram-entities` keys that carry a step. A fork has no label of its own, which is why
#: `_step_links` keeps its own shorter list — that one is about what can be *found* in a body.
STEP_KEYS: tuple[str, ...] = ("action", "decision", "fork", "partition")


def graph_from_declarations(
    diagram_entities: Mapping[str, object], diagram_connections: list[dict[str, object]]
) -> StepGraph:
    """The declared graph, read from one diagram's `diagram-entities` and its connections.

    **One reading, three callers.** The renderer builds the graph to walk it, a verification
    contribution builds it to ask what cannot be drawn, and the golden-shape tests build it to state
    what a shape is. All three reassembled it from the renderer's own privates — the tests literally
    imported five underscored names — and a second assembly of a declaration is the defect this
    repository's syntax register exists to prevent, arriving by the side door.

    What it does *not* do is decide anything: a second `step-flow` out of one step is silently lost
    here, exactly as it always was, and `colliding_declarations` is what reports that. Reading and
    judging stay apart.
    """
    return StepGraph(
        step_by_id=_steps_by_id(diagram_entities),
        flow_next=target_index(diagram_connections, "step-flow"),
        then_target=target_index(diagram_connections, "step-then"),
        else_target=target_index(diagram_connections, "step-else"),
        fork_branches=branch_index(diagram_connections, "step-fork-branch"),
        contains_first=target_index(diagram_connections, "step-contains"),
    )


def target_index(diagram_connections: list[dict[str, object]], conn_type: str) -> dict[str, str]:
    """One target per source for *conn_type*.

    **The one place an edge type is indexed one-per-source**, which is what makes that property
    checkable: `test_single_target_edge_types_match_the_index` reads the call sites here against the
    list W048 checks for collisions, and a type that quietly changed builder would otherwise have the
    diagnostic report a loss that no longer happens. The lane index is read through it too, because it
    loses a second edge exactly the same way.

    A second edge of this type out of one step is discarded, silently, before any walk runs. That is
    reported by `colliding_declarations`, not prevented here: reading and judging stay apart.
    """
    return {
        str(kc["source"]): str(kc["target"])
        for kc in diagram_connections
        if isinstance(kc, dict) and kc.get("conn_type") == conn_type
        and kc.get("source") and kc.get("target")
    }


def branch_index(diagram_connections: list[dict[str, object]], conn_type: str) -> dict[str, list[str]]:
    """Every target per source — the one type that does not lose a second edge."""
    result: dict[str, list[str]] = {}
    for kc in diagram_connections:
        if isinstance(kc, dict) and kc.get("conn_type") == conn_type and kc.get("source") and kc.get("target"):
            result.setdefault(str(kc["source"]), []).append(str(kc["target"]))
    return result


def _steps_by_id(kd: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key in STEP_KEYS:
        raw = kd.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("id"):
                    result[str(item["id"])] = {**item, "type": item.get("type") or key}
    return result


def branch_owned(graph: StepGraph) -> set[str]:
    owned = _branch_entries(graph)
    changed = True
    while changed:
        changed = False
        for src, tgt in graph.flow_next.items():
            if src in owned and tgt not in owned:
                owned.add(tgt)
                changed = True
    return owned


def _branch_entries(graph: StepGraph) -> set[str]:
    entries = (
        set(graph.then_target.values())
        | set(graph.else_target.values())
        | set(graph.contains_first.values())
    )
    for ids in graph.fork_branches.values():
        entries.update(ids)
    return entries


def entry_step(graph: StepGraph) -> str | None:
    """Where the walk starts: a step nothing flows into and no branch owns.

    Derives the owned set itself rather than taking it: it is a function of the graph, so a caller
    passing a stale or differently-built one is a mistake this signature simply does not permit.

    A back edge leaves no such step — every step of a retry loop is reached from somewhere — and
    returning None then drew `start` and `stop` with nothing between them. So a graph that loops
    falls back to a step no branch enters, and failing that to the first declared step: an entry
    into a cycle is a choice rather than a fact, and any of them draws the whole loop.
    """
    owned = branch_owned(graph)
    has_incoming_flow = set(graph.flow_next.values())
    for step_id in graph.step_by_id:
        if step_id not in owned and step_id not in has_incoming_flow:
            return step_id
    branch_entries = _branch_entries(graph)
    for step_id in graph.step_by_id:
        if step_id not in branch_entries:
            return step_id
    return next(iter(graph.step_by_id), None)
