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

from collections.abc import Mapping
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
    reachable from the other — through `reachable_including_merge`, because a decision's merge edge is
    somewhere control goes even though the *walk* must not treat it as a successor. Asking with the
    walk's reachability made every cycle running through a decision invisible, which is the ordinary
    retry shape. These graphs hold tens of steps, so the quadratic reading is the
    readable one and Tarjan's would be cleverness bought with nothing.

    A single step counts only if it reaches itself, which is a self-loop — the poll-until shape.
    """
    groups: list[frozenset[str]] = []
    placed: set[str] = set()
    for step_id in sorted(graph.step_by_id):
        if step_id in placed:
            continue
        onward = graph.reachable_including_merge(step_id) - {step_id}
        together = frozenset(
            {step_id}
            | {other for other in onward if step_id in graph.reachable_including_merge(other)}
        )
        if len(together) > 1 or step_id in graph.successors_including_merge(step_id):
            groups.append(together)
            placed |= together
    return tuple(groups)


def cycles_of(
    graph: StepGraph, lane_of: Mapping[str, str], *, start: str | None = None
) -> tuple[tuple[Loop, ...], tuple[UndrawableCycle, ...]]:
    """Every cycle the declared graph carries, split into the ones a `repeat` can draw and the rest.

    **A cycle, not a back edge.** Which edge of a cycle counts as the one going "back" depends on
    where a traversal started, so an answer phrased that way changes with the renderer's choice of
    root — tried, and it reported one loop three times, once per edge of the cycle. The cycle itself
    is a property of the graph: the steps that can each reach the other, the one among them that
    decides whether to go round again, and the one control arrives at.

    *lane_of* says which swimlane each step is in, and is a parameter for the same reason: it is read
    by `_step_graph.lane_of_step`, whose one indexing both callers share, so the renderer's decision
    about what it draws and the W049 report about what it refuses cannot drift apart. Required rather
    than defaulted, because a caller that forgot it would silently accept a loop whose way back is
    drawn through its own body — a check that fails open is worse than no check.

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
        loop, reason = _as_loop(graph, group, start, lane_of)
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


def _region_reaching(graph: StepGraph, start: str, stop_at: frozenset[str]) -> tuple[str, ...]:
    """*start* and every step reachable from it without passing through *stop_at*, in walk order.

    A region, not a chain, and the difference is the whole of what a body may hold. `_emit_loop` hands
    the body to `emit_until_join` with the condition as a stop, which draws a decision and its arms
    like any other step — so the acceptance criterion must describe *that* shape. Stated as a
    single-successor chain instead, it truncated at the first decision and the accounting invariant
    then refused the shape as unaccounted-for: the ordinary retry loop whose body holds a decision,
    which PlantUML draws correctly and this refused for a limit it does not have.
    """
    order: list[str] = []
    seen: set[str] = set()
    pending = [start]
    while pending:
        step_id = pending.pop(0)
        if step_id in seen or step_id in stop_at:
            continue
        seen.add(step_id)
        order.append(step_id)
        pending.extend(graph.successors_of(step_id))
    return tuple(order)


def _conditions_in(graph: StepGraph, group: frozenset[str]) -> tuple[str, ...]:
    """The decisions of *group* with exactly one arm inside it — the candidates for the loop's foot.

    **Not "the step with a successor outside the group".** That reading counted a decision in the
    *body* as a second exit, because its arms end in steps that never return and so are not part of
    the cycle. It is what refused every loop holding a decision. What distinguishes the foot of a loop
    is that one arm goes round again and the other does not: exactly one arm inside the cycle.
    """
    return tuple(
        step_id for step_id in sorted(group)
        if graph.kind_of(step_id) == "decision"
        and sum(
            1 for arm in (graph.then_target.get(step_id), graph.else_target.get(step_id))
            if arm in group
        ) == 1
    )


def _returns_into(graph: StepGraph, group: frozenset[str], header: str) -> tuple[str, ...]:
    """The steps of *group* that point at *header* — the loop's back edges.

    A `repeat` draws one return path. Two steps returning to one header is two back edges, which the
    notation cannot show and which rendered as a `repeat` with an empty arm and one return relocated
    into the body — a confident wrong picture. Counted here because the accounting invariant alone
    does not catch it: both returns *are* accounted for, one as the body and one as the way back.
    """
    return tuple(
        step_id for step_id in sorted(group)
        if header in graph.successors_including_merge(step_id)
    )


def _lanes_spanned(lane_of: Mapping[str, str], steps: frozenset[str]) -> tuple[str, ...]:
    """The distinct swimlanes *steps* are declared in, sorted. Empty where none are declared."""
    return tuple(sorted({lane for step_id in steps if (lane := lane_of.get(step_id)) is not None}))


def _cycle_left_after_the_way_back(
    graph: StepGraph, group: frozenset[str], header: str
) -> tuple[str, ...]:
    """The steps of a cycle that survives removing every way back to *header*, or empty.

    **One strongly connected component can hold more than one loop.** An inner retry nested inside an
    outer one is a single component: from the inner body you reach the outer header and back again. So
    the accounting invariant sees every step placed inside the shape and accepts it, while the inner
    return edge is drawn nowhere at all — the same silent drop the cycle finder exists to end, arrived
    at from the other direction.

    A `repeat` draws exactly one way round. Take those edges away, and what is left must be acyclic;
    anything else is a second loop with no notation to carry it.
    """
    onward = {
        step_id: [
            target for target in graph.successors_including_merge(step_id)
            if target in group and target != header
        ]
        for step_id in group
    }
    visiting: set[str] = set()
    settled: set[str] = set()
    trail: list[str] = []

    def descend(step_id: str) -> tuple[str, ...]:
        visiting.add(step_id)
        trail.append(step_id)
        for target in onward.get(step_id, ()):
            if target in visiting:
                return tuple(sorted(trail[trail.index(target):]))
            if target not in settled and (found := descend(target)):
                return found
        visiting.discard(step_id)
        settled.add(step_id)
        trail.pop()
        return ()

    for step_id in sorted(group):
        if step_id not in settled and (found := descend(step_id)):
            return found
    return ()


def _body_holding_what_follows(
    graph: StepGraph, body: tuple[str, ...], exit_target: str | None
) -> tuple[str, ...]:
    """Steps drawn inside the loop body that belong after the loop.

    The body is walked as a *region*, which is what lets a loop hold a decision — and the same walk
    will follow an arm out of the loop and pull what it finds in with it. A body arm flowing to a step
    that comes after the loop therefore draws that step, and its whole continuation, inside the
    `repeat`: the picture runs them on every pass, and the loop's exit draws nothing at all because
    what the exit points at has already been drawn above it.

    Measured, on the shape that exposed it: an arm reaching the step after the loop put both that step
    and the loop's exit inside the arm, and the flow read as looping forever with no way out. Asked of
    everything the exit reaches, not just the exit itself, because the continuation comes too.
    """
    if exit_target is None:
        return ()
    return tuple(sorted(graph.reachable_including_merge(exit_target) & set(body)))


def _as_loop(
    graph: StepGraph, group: frozenset[str], start: str | None, lane_of: Mapping[str, str]
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
    candidates = _conditions_in(graph, group)
    if len(candidates) != 1:
        return None, (
            "no decision in this loop has one arm going round again and the other leaving, so "
            "nothing chooses whether to run it again"
            if not candidates
            else f"{len(candidates)} decisions could each close this loop "
            f"({', '.join(candidates)}); a repeat has one condition at its foot"
        )
    condition = candidates[0]
    returns = _returns_into(graph, group, header)
    if len(returns) != 1:
        return None, (
            f"nothing inside this loop returns to {header!r}, so there is no way round to draw"
            if not returns
            else f"{len(returns)} steps return to {header!r} ({', '.join(returns)}), and a repeat "
            f"draws one way round. Drawing this showed a loop with an empty arm and one return "
            f"moved into the body — a picture the model does not describe"
        )
    # Measured, by rendering and reading the geometry: a `repeat` whose cycle spans two swimlanes has
    # its back edge routed straight through the boxes of its own body, terminating inside the header
    # rather than at its edge. The identical shape inside one lane draws correctly. So this is a limit
    # of the layout, not of the notation, and it is checked here because it decides drawability.
    lanes = _lanes_spanned(lane_of, group)
    if len(lanes) > 1:
        return None, (
            f"this loop runs through {len(lanes)} swimlanes ({', '.join(lanes)}), and a repeat "
            f"crossing a lane has its way back drawn through the steps it returns past — measured. "
            f"Keeping every step of the loop in one lane draws the same shape correctly"
        )
    arms = {"then": graph.then_target.get(condition), "else": graph.else_target.get(condition)}
    looping = [name for name, target in arms.items() if target in group]
    if len(looping) != 1:
        return None, f"both arms of {condition!r} stay inside the loop, so it has no exit to draw"
    arm = looping[0]
    body = _region_reaching(graph, header, stop_at=frozenset({condition}))
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
    inner = _cycle_left_after_the_way_back(graph, group, header)
    if inner:
        return None, (
            f"{', '.join(inner)} form a second loop inside this one, and a repeat draws one way "
            f"round. Nesting two loops in one cycle leaves the inner way back drawn nowhere at all"
        )
    exit_target = arms["else" if arm == "then" else "then"]
    already_drawn = _body_holding_what_follows(graph, body, exit_target)
    if already_drawn:
        return None, (
            f"{', '.join(already_drawn)} {'comes' if len(already_drawn) == 1 else 'come'} after this "
            f"loop and {'is' if len(already_drawn) == 1 else 'are'} also reached from inside its "
            f"body, so the walk draws {'it' if len(already_drawn) == 1 else 'them'} within the "
            f"repeat. The picture then runs the steps after the loop on every pass and shows no exit. "
            f"Let the body arm reach the loop's condition instead, and draw what follows once after it"
        )
    # Every step of the cycle has to be somewhere in the drawn shape, or the drawing is not of this
    # cycle. A `repeat` shows its header, the region walked from it, the condition and one returning
    # step; a group holding anything else has a branch the walk does not reach, and it was being
    # claimed as drawable.
    accounted = {header, condition, *body, *backward}
    unaccounted = tuple(sorted(group - accounted))
    if unaccounted:
        return None, (
            f"{', '.join(unaccounted)} {'is' if len(unaccounted) == 1 else 'are'} inside this loop "
            f"and outside the shape a repeat draws — its header, the steps walked from it, the "
            f"condition, and one step on the way back. A branch the walk does not reach cannot be "
            f"drawn, and drawing the rest would show a loop this is not"
        )
    return Loop(
        header=header,
        body=body,
        condition=condition,
        looping_arm=arm,
        backward=backward,
        exit_target=exit_target,
    ), ""
