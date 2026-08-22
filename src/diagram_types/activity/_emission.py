"""The activity emission walk — the declared step graph turned into PlantUML activity lines.

Split out of ``renderer.py``, which had grown past the project's LoC limit. The renderer builds
the indices and the preamble; this module walks the graph and appends the body lines. The walk's
one piece of mutable state is which swimlane it is currently in, which is why `LaneCursor` exists
and nothing else here is mutable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ._step_links import link_suffix, sentinel_wrapped, user_link_suffix


@dataclass(frozen=True)
class StepGraph:
    """Which steps the diagram declares, and where control goes from each of them."""

    step_by_id: Mapping[str, dict[str, Any]]
    flow_next: Mapping[str, str]
    then_target: Mapping[str, str]
    else_target: Mapping[str, str]
    fork_branches: Mapping[str, Sequence[str]]
    contains_first: Mapping[str, str]


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


def emit_from(start_id: str, ctx: EmissionContext, lines: list[str], visited: set[str]) -> None:
    emit_until_join(start_id, ctx, lines, visited)


def emit_until_join(
    start_id: str, ctx: EmissionContext, lines: list[str], visited: set[str]
) -> str | None:
    """Emit from *start_id* onward, stopping at a join. Returns the join, or None if none was met.

    A branch of a fork ends where it reaches the join; the continuation beyond it belongs to the
    fork as a whole and is emitted once, by whoever opened it.
    """
    step_id: str | None = start_id
    while step_id and step_id not in visited:
        if is_join(step_id, ctx):
            return step_id
        step = ctx.graph.step_by_id.get(step_id)
        if not step:
            break
        visited.add(step_id)
        _emit_step(step, step_id, ctx, lines, visited)
        step_id = ctx.graph.flow_next.get(step_id)
    return None


def emit_orphans(
    branch_owned: set[str], ctx: EmissionContext, lines: list[str], visited: set[str]
) -> None:
    for step_id in ctx.graph.step_by_id:
        if step_id not in branch_owned and step_id not in visited:
            emit_from(step_id, ctx, lines, visited)


def _emit_step(
    step: dict[str, Any], step_id: str, ctx: EmissionContext, lines: list[str], visited: set[str]
) -> None:
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
        if then_first:
            emit_from(then_first, ctx, lines, visited)
        lines.append(f"else ({else_label})")
        else_first = ctx.graph.else_target.get(step_id)
        if else_first:
            emit_from(else_first, ctx, lines, visited)
        lines.append("endif")

    elif stype == "fork":
        # No sentinel link here: PlantUML's `fork` keyword takes no label/link argument at
        # all (`fork [[url]]` is a syntax error) and renders as an unlabeled, ungrouped bar
        # with no distinguishing SVG attribute — forks are not selectable in the viewer.
        _maybe_switch_lane(step_id, ctx, lines)
        branches = ctx.graph.fork_branches.get(step_id) or ()
        if branches:
            lines.append("fork")
            _emit_step_note(step_id, ctx, lines)
            # Each branch walks its own path — hence the copied `visited` — and stops where it
            # reaches the join. Without that stop every branch ran on to the end of the graph, so
            # the whole continuation was repeated once per branch and nested forks multiplied it.
            joins: list[str] = []
            for i, branch_start in enumerate(branches):
                if i > 0:
                    lines.append("fork again")
                reached = emit_until_join(branch_start, ctx, lines, set(visited))
                if reached is not None:
                    joins.append(reached)
            lines.append("end fork")
            # The continuation belongs to the fork, not to any branch, so it is emitted once here.
            # A branch that never reaches the join contributes nothing to this; the first join any
            # branch did reach is the one the fork closes on.
            if joins:
                join_id = joins[0]
                visited.add(join_id)
                after_join = ctx.graph.flow_next.get(join_id)
                if after_join:
                    emit_from(after_join, ctx, lines, visited)

    elif stype == "partition":
        label = puml_text(str(step.get("label") or "Partition"))
        lines.append(f'partition "{label}"{link_suffix(step)} {{')
        _emit_step_note(step_id, ctx, lines)
        contains_id = ctx.graph.contains_first.get(step_id)
        if contains_id:
            emit_from(contains_id, ctx, lines, visited)
        lines.append("}")


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
        lines.append(f"|{puml_text(str(lane.get('label') or lane['id']))}|")
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


def puml_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace("|", "/")
