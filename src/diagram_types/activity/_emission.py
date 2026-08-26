"""The activity emission walk — the declared step graph turned into PlantUML activity lines.

Split out of ``renderer.py``, which had grown past the project's LoC limit. The renderer builds
the indices and the preamble; this module walks the graph and appends the body lines. The walk's
one piece of mutable state is which swimlane it is currently in, which is why `LaneCursor` exists
and nothing else here is mutable.

**Where a convergent step is drawn.** A step more than one branch reaches has exactly one right
placement, and which one depends on the shape:

* every arm of a decision reaches it, and no path out of the decision escapes it — it is drawn once
  after that decision's `endif`, and each arm stops where it arrives (`_convergence_point`);
* the same for a fork's branches, drawn once past `end fork`, whether or not the model declares a
  join step for them to meet at;
* the arrivals sit at different nesting depths and neither escapes the other — nothing structured
  covers exactly those paths, so the step is **drawn in each branch that arrives at it**, along with
  whatever follows it there.

Post-dominance, not mere reachability, is what separates the first two from the third. A step both
arms *can* reach may still be escaped by a path through one of them, and hoisting it past the
`endif` would then put it on a path that never had it.

Convergence itself is `_step_graph`'s question, not this module's.

**Why the third case duplicates.** Two alternatives were tried and both are worse. `label` / `goto`
would state the arrival directly, and on the pinned PlantUML 1.2026.3 both are accepted and then
ignored — a backward `goto` draws an arrow to the following node, and inside a branch it leaves a
dangling arrowhead. A flowchart connector pair renders correctly and is unreadable here: it puts an
unlabelled circle in a viewer where every element is expected to be clickable and to resolve to the
artifact it stands for, and the circle resolves to nothing. A second drawing of the step carries the
same `arch://` sentinel as the first, so both are selectable and both resolve to one artifact, which
is what a reader of this diagram needs.

**What stops that from multiplying.** The walk carries the chain of steps it is currently inside, and
a step already on that chain ends the walk instead of being drawn again — so a back edge closes
rather than recurring. Duplication is therefore bounded by the number of branches that arrive at a
step from outside, which is the number of times a reader would expect to see it.

**A cycle is drawn as a `repeat`, not closed silently.** Ending the walk at the returning step left a
picture that said the flow falls straight through — the opposite of what the model declared, with
every step present so no coverage rule noticed. Where `_step_graph` recognises a drawable loop, the
walk emits `repeat` / `backward:` / `repeat while (…) is (…) not (…)` and carries on from the exit.
The condition is *consumed* by the `repeat while` line, so it is marked drawn and never also emitted
as an `if`. Where the cycle is not one of the drawable shapes the walk still closes it as before,
and `_contributions` reports why rather than leaving a reader to notice by eye.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ._step_cycles import Loop
from ._step_graph import StepGraph
from ._step_links import (
    lane_header,
    link_suffix,
    puml_text,
    sentinel_wrapped,
    user_link_suffix,
)


@dataclass
class LaneCursor:
    """Which swimlane the emission is currently in — the only thing the walk mutates."""

    current: str | None


@dataclass(frozen=True)
class Swimlanes:
    """The lane a step belongs to, the lanes themselves, and where the emission stands."""

    index: Mapping[str, str]
    by_id: Mapping[str, dict[str, Any]]
    declared: bool
    cursor: LaneCursor


@dataclass(frozen=True)
class EmissionContext:
    """Everything the walk reads. Passed whole so no emission function grows a parameter list."""

    graph: StepGraph
    lanes: Swimlanes
    notes: Mapping[str, dict[str, Any]]
    #: The drawable loops of this graph, keyed by the step each one opens at. Computed once by the
    #: renderer with the root it chose, because which step a cycle is entered at is that choice.
    loops: Mapping[str, Loop] = field(default_factory=dict)


def is_join(step_id: str, ctx: EmissionContext) -> bool:
    """A join is a fork-typed step that opens no branches — the bar the branches converge on.

    The model spells a fork and a join the same way, in `diagram_entities.fork[]`; what tells them
    apart is that a fork has outgoing `step-fork-branch` connections and a join has only incoming
    `step-flow`. That is why the join used to vanish: with no branches it emitted nothing, and the
    walk carried straight on through the continuation — once per branch.
    """
    step = ctx.graph.step_by_id.get(step_id)
    if step is None:
        return False
    return str(step.get("type") or "") == "fork" and not ctx.graph.fork_branches.get(step_id)


def emit_from(
    start_id: str,
    ctx: EmissionContext,
    lines: list[str],
    drawn: set[str],
    stops: frozenset[str] = frozenset(),
    path: frozenset[str] = frozenset(),
) -> None:
    """Emit from *start_id* where no fork is waiting on a join, so one met here is owed to nobody.

    The four callers are the root walk, the pass over what it did not reach, and a fork's own
    continuation past its own join. Kept as its own name rather than folded into `emit_until_join`
    because discarding that return **silently** is the defect this release fixed: the name is where a
    reader learns the discard is the contract and not an oversight.
    """
    emit_until_join(start_id, ctx, lines, drawn, stops, path)


def emit_until_join(
    start_id: str,
    ctx: EmissionContext,
    lines: list[str],
    drawn: set[str],
    stops: frozenset[str] = frozenset(),
    path: frozenset[str] = frozenset(),
) -> str | None:
    """Emit from *start_id* onward, stopping at a join. Returns the join, or None if none was met.

    A branch of a fork ends where it reaches the join; the continuation beyond it belongs to the
    fork as a whole and is emitted once, by whoever opened it. *stops* carries the convergence
    points of every construct this walk is inside, so an arm ends where its enclosing decision or
    fork will draw the step it arrived at.

    *path* is the chain of steps this walk is inside. It, and not the set of everything drawn so far,
    is what ends the walk — so a step another branch already drew is drawn again here, and a step
    this walk is already inside is not. `drawn` only records what has been drawn at all, for the
    pass over whatever the walk never reached.
    """
    graph = ctx.graph
    step_id: str | None = start_id
    # A join reached *by* this walk belongs to the fork that opened it, and is handed back. A join
    # this walk was sent to, because it is the convergence point of the construct just emitted, is
    # already that construct's own — so the walk carries on through it instead of handing it up.
    resumed_at_convergence = False
    surfaced_join: str | None = None
    walked = path
    while step_id and step_id not in stops and step_id not in walked:
        if is_join(step_id, ctx) and not resumed_at_convergence:
            return step_id
        loop = ctx.loops.get(step_id)
        if loop is not None and step_id not in drawn:
            # The whole loop is emitted here, condition included, and the walk resumes past it. Only
            # when the header has not been drawn: a loop reached a second time from another branch is
            # an ordinary revisit, and re-opening `repeat` would draw the cycle twice.
            step_id = _emit_loop(loop, ctx, lines, drawn, stops, walked)
            walked = walked | frozenset(loop.body) | {loop.condition}
            resumed_at_convergence = False
            continue
        step = graph.step_by_id.get(step_id)
        if not step:
            break
        drawn.add(step_id)
        walked = walked | {step_id}
        convergence = graph.convergence_point(step_id)
        arm_stops = stops | ({convergence} if convergence else frozenset())
        surfaced = _emit_step(step, step_id, ctx, lines, drawn, arm_stops, walked)
        if surfaced is not None and surfaced_join is None:
            # A join reached inside the construct just emitted belongs to the fork that opened it,
            # which may be several levels out. Without this channel it was lost, and everything past
            # the join went undrawn. The walk carries on rather than returning here: one arm leaving
            # for the join says nothing about the other arm, whose own merge is still to be drawn.
            surfaced_join = surfaced
        resumed_at_convergence = convergence is not None
        step_id = convergence or graph.flow_next.get(step_id)
    return surfaced_join


def _emit_loop(
    loop: Loop,
    ctx: EmissionContext,
    lines: list[str],
    drawn: set[str],
    stops: frozenset[str],
    path: frozenset[str],
) -> str | None:
    """Emit *loop* as a `repeat`, and hand back where the flow continues.

    The body is walked by the ordinary emission with the condition as a stop, so a step inside a loop
    is drawn by the same code as a step outside one — including its lane switches, its note and any
    decision or fork nested within it.

    `backward:` carries the single step on the way round. One, because a second `backward:` line
    renders nothing at all on the pinned PlantUML — measured, with a clean render and no warning — so
    `_step_graph` refuses a longer return path rather than letting it be lost here.
    """
    graph = ctx.graph
    condition_step = graph.step_by_id.get(loop.condition) or {}
    lines.append("repeat")
    # Marked before the body is walked, because the walk asks `ctx.loops` at every step and would
    # otherwise re-open this same `repeat` on reaching the header again — endlessly. The mark does not
    # suppress the header's own emission: the walk decides that from the path it carries, not from
    # what has been drawn.
    drawn.add(loop.header)
    emit_until_join(loop.header, ctx, lines, drawn, stops | {loop.condition}, path)
    for step_id in loop.backward:
        step = graph.step_by_id.get(step_id)
        if step is None:
            continue
        drawn.add(step_id)
        label = puml_text(str(step.get("label") or "action"))
        lines.append(f"backward:{sentinel_wrapped(step, label)}{user_link_suffix(step)};")
    # Marked drawn *by* this line: the condition is the diamond at the foot of the loop, so nothing
    # else may draw it — and `emit_orphans` would otherwise find it unemitted and draw it again.
    drawn.add(loop.condition)
    condition = puml_text(str(condition_step.get("condition") or "?"))
    then_label = puml_text(str(condition_step.get("then_label") or "yes"))
    else_label = puml_text(str(condition_step.get("else_label") or "no"))
    going_round, leaving = (
        (then_label, else_label) if loop.looping_arm == "then" else (else_label, then_label)
    )
    lines.append(
        f"repeat while ({sentinel_wrapped(condition_step, f'{condition}?')}"
        f"{user_link_suffix(condition_step)}) is ({going_round}) not ({leaving})"
    )
    return loop.exit_target


def emit_orphans(
    branch_owned: set[str], ctx: EmissionContext, lines: list[str], drawn: set[str]
) -> None:
    """Draw whatever the walk from the root did not reach.

    Chain heads first, so a second disconnected chain is drawn from its start rather than from
    whichever of its steps happens to be declared first. Then anything still unemitted, which is
    what a step graph reachable only through a back edge comes down to: every step of a cycle is
    owned by a branch, so nothing in it is a head.
    """
    for step_id in ctx.graph.step_by_id:
        if step_id not in branch_owned and step_id not in drawn:
            emit_from(step_id, ctx, lines, drawn)
    for step_id in ctx.graph.step_by_id:
        if step_id not in drawn:
            emit_from(step_id, ctx, lines, drawn)


def _emit_step(
    step: dict[str, Any],
    step_id: str,
    ctx: EmissionContext,
    lines: list[str],
    drawn: set[str],
    stops: frozenset[str],
    path: frozenset[str],
) -> str | None:
    """Emit this step, and hand back a join reached inside it for an enclosing fork to close on."""
    stype = str(step.get("type") or "")

    if stype == "action":
        _maybe_switch_lane(step_id, ctx, lines)
        label = puml_text(str(step.get("label") or "action"))
        lines.append(f":{sentinel_wrapped(step, label)}{user_link_suffix(step)};")
        _emit_step_note(step_id, ctx, lines)

    elif stype == "decision":
        _maybe_switch_lane(step_id, ctx, lines)
        condition = puml_text(str(step.get("condition") or "?"))
        then_label = puml_text(str(step.get("then_label") or "yes"))
        else_label = puml_text(str(step.get("else_label") or "no"))
        # Before the `if`, never inside the then-branch. A note emitted after `then (...)` sits in a
        # branch, and a branch that switches lane renders the note once per lane — so a note on a
        # decision appeared twice while a note on an action appeared once. Measured on a minimal
        # two-lane diagram: inside-branch 2, floating-inside-branch 2, before-the-if 1.
        _emit_step_note(step_id, ctx, lines)
        lines.append(
            f"if ({sentinel_wrapped(step, f'{condition}?')}{user_link_suffix(step)}) then ({then_label})"
        )
        then_first = ctx.graph.then_target.get(step_id)
        from_then = emit_until_join(then_first, ctx, lines, drawn, stops, path) if then_first else None
        lines.append(f"else ({else_label})")
        else_first = ctx.graph.else_target.get(step_id)
        from_else = emit_until_join(else_first, ctx, lines, drawn, stops, path) if else_first else None
        lines.append("endif")
        return from_then or from_else

    elif stype == "fork":
        # No sentinel link here: PlantUML's `fork` keyword takes no label/link argument at
        # all (`fork [[url]]` is a syntax error) and renders as an unlabeled, ungrouped bar
        # with no distinguishing SVG attribute — forks are not selectable in the viewer.
        branches = ctx.graph.fork_branches.get(step_id) or ()
        if branches:
            # Only a fork switches lane. A join emits nothing at all, so a lane switch before one
            # would be a bar in a lane with no activity in it.
            _maybe_switch_lane(step_id, ctx, lines)
            _emit_fork(step_id, branches, ctx, lines, drawn, stops, path)
            # A fork consumes its own join and must not hand it to an enclosing fork.
            return None

    elif stype == "partition":
        label = puml_text(str(step.get("label") or "Partition"))
        lines.append(f'partition "{label}"{link_suffix(step)} {{')
        _emit_step_note(step_id, ctx, lines)
        contains_id = ctx.graph.contains_first.get(step_id)
        inside = emit_until_join(contains_id, ctx, lines, drawn, stops, path) if contains_id else None
        lines.append("}")
        return inside


def _emit_fork(
    step_id: str,
    branches: Sequence[str],
    ctx: EmissionContext,
    lines: list[str],
    drawn: set[str],
    stops: frozenset[str],
    path: frozenset[str],
) -> None:
    lines.append("fork")
    _emit_step_note(step_id, ctx, lines)
    # Each branch stops where it reaches the join or the step every branch converges on. Without
    # that stop every branch ran on to the end of the graph, so the whole continuation was repeated
    # once per branch and nested forks multiplied it.
    joins: list[str] = []
    for index, branch_start in enumerate(branches):
        if index > 0:
            lines.append("fork again")
        reached = emit_until_join(branch_start, ctx, lines, drawn, stops, path)
        if reached is not None:
            joins.append(reached)
    lines.append("end fork")
    # The continuation belongs to the fork, not to any branch, so it is emitted once here. A branch
    # that never reaches the join contributes nothing to this; the first join any branch did reach
    # is the one the fork closes on. Where the branches converge instead, the walk that opened this
    # fork continues at the convergence point and this is not reached.
    if joins:
        join_id = joins[0]
        drawn.add(join_id)
        after_join = ctx.graph.flow_next.get(join_id)
        if after_join:
            emit_from(after_join, ctx, lines, drawn, stops, path | {join_id})


def _maybe_switch_lane(step_id: str, ctx: EmissionContext, lines: list[str]) -> None:
    lanes = ctx.lanes
    lane_id = lanes.index.get(step_id)
    if not lane_id:
        if lanes.declared and step_id:
            lines.append(f"' WARNING: step '{step_id}' has no step-in-lane connection")
        return
    if lane_id == lanes.cursor.current:
        return
    lane = lanes.by_id.get(lane_id)
    if lane:
        lines.append(lane_header(lane))
        lanes.cursor.current = lane_id


def _emit_step_note(step_id: str, ctx: EmissionContext, lines: list[str]) -> None:
    note = ctx.notes.get(step_id)
    if not note:
        return
    side = str(note.get("side") or "right")
    if side not in ("left", "right"):
        side = "right"
    text = str(note.get("text") or "")
    if not text:
        return
    if "\n" in text:
        lines.append(f"note {side}")
        for note_line in text.split("\n"):
            lines.append(puml_text(note_line))
        lines.append("end note")
    else:
        lines.append(f"note {side}: {puml_text(text)}")


