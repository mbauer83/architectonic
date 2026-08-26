"""Which cycles a declared step graph carries, and whether a `repeat` can draw each.

Beside `_step_graph` rather than in it: the graph answers "where can control go from here", and this
answers "does this graph loop, and can that loop be drawn". Together with `_edge_collisions` they were
one module until it held three concerns under one name.

**A refusal is a deliverable.** The alternative is what shipped before: the walk stopped at the
returning step, nothing was drawn, and the picture asserted that the flow fell straight through — the
opposite of what the model declared, with every step present so no coverage rule noticed. Every cycle
here is either matched to a drawable shape or refused with a reason a reader can act on.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._step_graph import StepGraph


@dataclass(frozen=True)
class Loop:
    """A cycle in the declared graph that a structured `repeat` can draw faithfully.

    The shape is the one an author writes when a decision sends work back: `header` is where control
    returns to, `body` runs from there to the `condition`, and one of the condition's arms goes round
    again through `backward` while the other leaves. PlantUML draws exactly that with
    `repeat` / `backward:` / `repeat while (…) is (…) not (…)`.

    The condition is *consumed* by the `repeat while` line — it is the diamond at the foot of the
    loop — so an emission that draws this must not also draw it as an `if`.
    """

    header: str
    #: `header` and whatever follows it up to but excluding the condition, in traversal order.
    body: tuple[str, ...]
    #: The decision whose arms decide whether to go round again.
    condition: str
    #: Which of the condition's arms returns to the header: `"then"` or `"else"`.
    looping_arm: str
    #: The steps traversed on the way back, in order. Empty where the condition returns directly.
    backward: tuple[str, ...]
    #: Where control goes once the loop ends, or None where the loop is the end of the flow.
    exit_target: str | None


@dataclass(frozen=True)
class UndrawableCycle:
    """A cycle the structured forms cannot express, and why.

    A refusal is a deliverable. The alternative is what 0.7.1 shipped: the walk stops at the returning
    step, nothing is drawn, and the picture asserts that the flow falls through — the opposite of what
    the model says — with every step present so no coverage rule notices.
    """

    #: The steps the cycle runs through, sorted. Named as a set rather than as an edge because which
    #: edge "goes back" depends on where a traversal started, and the cycle does not.
    steps: tuple[str, ...]
    reason: str


def _single_successor_chain(graph: StepGraph, start: str, stop_at: frozenset[str]) -> tuple[str, ...]:
    """*start* and each step reachable from it by exactly one successor, until a branch or a stop.

    A chain, not a traversal: the moment a step offers two ways on, the chain ends and the caller
    decides what that branching means. Guarded against a cycle by `stop_at` plus its own visited set,
    since the graphs this reads are the cyclic ones.
    """
    chain: list[str] = []
    seen: set[str] = set()
    step_id: str | None = start
    while step_id and step_id not in seen and step_id not in stop_at:
        chain.append(step_id)
        seen.add(step_id)
        successors = graph.successors_of(step_id)
        step_id = successors[0] if len(successors) == 1 else None
    return tuple(chain)


def _cyclic_groups(graph: StepGraph) -> tuple[frozenset[str], ...]:
    """The sets of steps that can each reach the other — one per cycle in the declared graph.

    Strongly connected components, computed the simple way: two steps share one when each is
    reachable from the other. These graphs hold tens of steps, so the quadratic reading is the
    readable one and Tarjan's would be cleverness bought with nothing.

    A single step counts only if it reaches itself, which is a self-loop — the poll-until shape.
    """
    groups: list[frozenset[str]] = []
    placed: set[str] = set()
    for step_id in sorted(graph.step_by_id):
        if step_id in placed:
            continue
        onward = graph.reachable_from(step_id) - {step_id}
        together = frozenset(
            {step_id} | {other for other in onward if step_id in graph.reachable_from(other)}
        )
        if len(together) > 1 or step_id in graph.successors_of(step_id):
            groups.append(together)
            placed |= together
    return tuple(groups)


def cycles_of(
    graph: StepGraph, *, start: str | None = None
) -> tuple[tuple[Loop, ...], tuple[UndrawableCycle, ...]]:
    """Every cycle the declared graph carries, split into the ones a `repeat` can draw and the rest.

    **A cycle, not a back edge.** Which edge of a cycle counts as the one going "back" depends on
    where a traversal started, so an answer phrased that way changes with the renderer's choice of
    root — tried, and it reported one loop three times, once per edge of the cycle. The cycle itself
    is a property of the graph: the steps that can each reach the other, the one among them that
    decides whether to go round again, and the one control arrives at.

    *start* is where the flow begins, and it is a parameter rather than something derived here because
    `_find_root` already says why: "an entry into a cycle is a choice rather than a fact, and any of
    them draws the whole loop". A cycle nothing outside points into has no intrinsic head, so the
    caller's choice is the answer — and deriving a second one here would be two roots that must agree.

    Returned as one pair because the two halves are one enumeration: a cycle is either matched to a
    drawable shape or refused with a reason, and a cycle that is neither would be one the caller
    silently drops — which is the defect this exists to end.
    """
    drawable: list[Loop] = []
    refused: list[UndrawableCycle] = []
    for group in _cyclic_groups(graph):
        loop, reason = _as_loop(graph, group, start)
        if loop is not None:
            drawable.append(loop)
        else:
            refused.append(UndrawableCycle(steps=tuple(sorted(group)), reason=reason))
    return tuple(drawable), tuple(refused)


def _entries_into(graph: StepGraph, group: frozenset[str], start: str | None) -> tuple[str, ...]:
    """The steps of *group* control can arrive at: from outside it, or because the flow starts there.

    Every step of a cycle has something pointing at it — that is what makes it a cycle — so "the one
    nothing points at" finds none, which is the bug this replaced. Where nothing *outside* points in,
    the flow begins inside, and the head is the caller's start.
    """
    from_outside = {
        target
        for source in graph.step_by_id
        if source not in group
        for target in graph.successors_of(source)
        if target in group
    }
    if from_outside:
        return tuple(sorted(from_outside))
    return (start,) if start in group else ()


def _as_loop(
    graph: StepGraph, group: frozenset[str], start: str | None
) -> tuple[Loop | None, str]:
    """*group* as a drawable loop, or None with the reason it is not.

    Each refusal names what a reader would otherwise have to notice by eye, because the picture for an
    undrawn cycle is not blank — it asserts that the flow falls straight through.
    """
    entries = _entries_into(graph, group, start)
    if len(entries) != 1:
        return None, (
            "nothing outside this loop reaches it and the flow does not start inside it, so it is "
            "drawn from nowhere"
            if not entries
            else f"control enters this loop at {len(entries)} steps ({', '.join(entries)}); "
            "a repeat has one head"
        )
    header = entries[0]
    leaving = tuple(
        step for step in sorted(group)
        if any(target not in group for target in graph.successors_of(step))
    )
    if len(leaving) != 1:
        return None, (
            "this loop never leaves, so there is no exit to draw"
            if not leaving
            else f"{len(leaving)} steps leave this loop ({', '.join(leaving)}); a repeat has one exit"
        )
    condition = leaving[0]
    if graph.kind_of(condition) != "decision":
        return None, (
            f"the loop leaves from {condition!r}, which is a {graph.kind_of(condition) or 'step'} "
            f"rather than a decision, so nothing chooses whether to run it again"
        )
    arms = {"then": graph.then_target.get(condition), "else": graph.else_target.get(condition)}
    looping = [name for name, target in arms.items() if target in group]
    if len(looping) != 1:
        return None, f"both arms of {condition!r} stay inside the loop, so it has no exit to draw"
    arm = looping[0]
    body = _single_successor_chain(graph, header, stop_at=frozenset({condition}))
    if condition in body:
        return None, f"the loop body from {header!r} does not reach {condition!r} in a single chain"
    backward_start = arms[arm]
    backward = (
        _single_successor_chain(graph, str(backward_start), stop_at=frozenset({header}))
        if backward_start
        else ()
    )
    if len(backward) > 1:
        return None, (
            f"{len(backward)} steps run on the way back to {header!r} ({', '.join(backward)}), and a "
            f"drawing carries one. A second `backward:` line renders nothing at all — measured, with "
            f"a clean render and no warning — so drawing this would lose "
            f"{', '.join(list(backward)[:-1])} silently"
        )
    return Loop(
        header=header,
        body=body,
        condition=condition,
        looping_arm=arm,
        backward=backward,
        exit_target=arms["else" if arm == "then" else "then"],
    ), ""
