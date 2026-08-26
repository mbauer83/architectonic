"""Every step the model declares is drawn exactly once, in the branch that reaches it.

Four assertions, stated over the shapes the notation permits rather than over the shape that
broke. The order they are written in is the order they were *measured* in, and it matters:

* **Coverage** — every declared step is drawn. Blind on its own: the bundled diagram drew all
  thirteen of its steps while telling a reader that nothing happens when the two ends are not yet
  typed.
* **A bound on repetition** — a step is drawn no more often than the model gives it ways in. Where
  two branches arrive at a step and no single structured placement covers both, the step is drawn in
  each of them, which is how a reader sees that both paths reach it; drawing it more often than it
  has arrivals is the fork-multiplication defect, where one tail appeared once per branch.
* **Every drawing is the step itself** — a full labelled line, never a connector or a jump. A
  flowchart connector renders correctly and is unreadable in this viewer: it puts an unlabelled
  circle where every element is expected to be clickable and to resolve to an artifact, and the
  circle resolves to nothing.
* **Per-branch coverage** — the one that goes red on the bundled diagram. A branch's first step is
  drawn inside that branch's own region, or hoisted past the construct's own `endif`/`end fork`
  because every arm converges on it.
* **Structure** — a step every arm of a decision reaches is not drawn inside one arm.

Coverage is stated over the step kinds that emit a *labelled* line — action, decision, partition.
A fork emits the bare `fork` keyword, which PlantUML gives no label or link argument, so a naive
"every declared step exactly once" is permanently red on every fork diagram.

The structural and per-branch assertions need a nesting-aware parse of the emitted body, which is
what `_parse` is. It lives in the test tree, and reads the body this project emits rather than any
stored syntax.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pytest

from src.diagram_types.activity._step_cycles import cycles_of
from src.diagram_types.activity._step_graph import StepGraph
from src.diagram_types.activity._step_links import sentinel_of
from src.diagram_types.activity.renderer import (
    _branch_owned_set,
    _build_multi_target,
    _build_single_target,
    _build_step_by_id,
    _find_root,
)
from tests.diagram_types._activity_shapes import CATALOGUE, ActivityShape, bundled_shapes

_LABELLED_KINDS = ("action", "decision", "partition")


# ── a nesting-aware parse of an emitted body ─────────────────────────────────


@dataclass
class Region:
    """One arm of a construct, or the body itself: the nodes emitted in sequence inside it."""

    nodes: list["Node"] = field(default_factory=list)


@dataclass
class Node:
    kind: str
    step_id: str | None = None
    regions: list[Region] = field(default_factory=lambda: [Region()])


def _parse(body: str) -> Node:
    """The emitted body as a tree of regions."""
    root = Node("root")
    stack = [root]
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("if ("):
            node = Node("decision", sentinel_of(line))
            stack[-1].regions[-1].nodes.append(node)
            stack.append(node)
        elif line.startswith("else ("):
            stack[-1].regions.append(Region())
        elif line == "endif":
            stack.pop()
        elif line == "fork":
            node = Node("fork")
            stack[-1].regions[-1].nodes.append(node)
            stack.append(node)
        elif line == "fork again":
            stack[-1].regions.append(Region())
        elif line in ("end fork", "endfork"):
            stack.pop()
        elif line.startswith("partition "):
            node = Node("partition", sentinel_of(line))
            stack[-1].regions[-1].nodes.append(node)
            stack.append(node)
        elif line == "}":
            if len(stack) > 1:
                stack.pop()
        elif line == "repeat":
            node = Node("loop")
            stack[-1].regions[-1].nodes.append(node)
            stack.append(node)
        elif line.startswith("repeat while ("):
            # The condition is drawn *by* this line — it is the diamond at the foot of the loop — so
            # the step it stands for is a node of the loop, and the line also closes the loop.
            stack[-1].regions[-1].nodes.append(Node("step", sentinel_of(line)))
            stack.pop()
        elif line.startswith("backward:") and line.endswith(";"):
            stack[-1].regions[-1].nodes.append(Node("step", sentinel_of(line)))
        elif line.startswith(":") and line.endswith(";"):
            stack[-1].regions[-1].nodes.append(Node("step", sentinel_of(line)))
    return root


def _drawn_steps(node: Node) -> list[str]:
    """Every step id the body draws, in emission order, including a second drawing of one."""
    found: list[str] = []
    for region in node.regions:
        for child in region.nodes:
            if child.kind in ("decision", "partition") and child.step_id:
                found.append(child.step_id)
            if child.kind == "step" and child.step_id:
                found.append(child.step_id)
            elif child.kind in ("decision", "fork", "partition", "loop"):
                found.extend(_drawn_steps(child))
    return found


def _reached_in(region: Region) -> set[str]:
    """The steps this region draws or jumps to, at any depth inside it."""
    reached: set[str] = set()
    for child in region.nodes:
        if child.step_id and child.kind in ("step", "decision", "partition"):
            reached.add(child.step_id)
        if child.kind in ("decision", "fork", "partition"):
            for inner in child.regions:
                reached |= _reached_in(inner)
    return reached


def _find_construct(node: Node, kind: str, step_id: str | None) -> tuple[Node, Region] | None:
    """The construct node with this id, and the region that holds it."""
    for region in node.regions:
        for child in region.nodes:
            if child.kind == kind and child.step_id == step_id:
                return child, region
            if child.kind in ("decision", "fork", "partition"):
                found = _find_construct(child, kind, step_id)
                if found:
                    return found
    return None


def _fork_nodes(node: Node) -> list[Node]:
    found: list[Node] = []
    for region in node.regions:
        for child in region.nodes:
            if child.kind == "fork":
                found.append(child)
            if child.kind in ("decision", "fork", "partition"):
                found.extend(_fork_nodes(child))
    return found


def _step_after(holder: Region, construct: Node) -> str | None:
    """The step drawn immediately after *construct* in its own region — the hoisted convergence."""
    nodes = holder.nodes
    at = nodes.index(construct)
    for following in nodes[at + 1:]:
        if following.kind == "step":
            return following.step_id
        if following.kind in ("decision", "partition"):
            return following.step_id
        return None
    return None


def _forks_placing(tree: Node, firsts: list[str], labelled: set[str]) -> list[Node]:
    """The emitted `fork` nodes whose regions hold these branches, in order.

    A fork emits the bare keyword with no sentinel, so it has no identity in the body. Region count
    plus the branches each region holds is what distinguishes one fork from another; where that is
    still ambiguous the property being asserted holds for any of them, which is a weakening this
    notation leaves no way around.
    """
    return [
        node for node in _fork_nodes(tree)
        if len(node.regions) == len(firsts)
        and all(
            first not in labelled or first in _reached_in(region) or not region.nodes
            for first, region in zip(firsts, node.regions, strict=True)
        )
    ]


# ── the declared graph, as the test reads it ─────────────────────────────────


def _declared(shape: ActivityShape, kinds: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for kind in kinds:
        raw = shape.entities.get(kind)
        if isinstance(raw, list):
            found.extend(str(item["id"]) for item in raw if isinstance(item, dict) and item.get("id"))
    return found


def _edges(shape: ActivityShape, conn_type: str) -> list[tuple[str, str]]:
    return [(str(c["source"]), str(c["target"])) for c in shape.connections if c.get("conn_type") == conn_type]


def _successors(shape: ActivityShape) -> dict[str, list[str]]:
    successors: dict[str, list[str]] = {}
    for conn_type in ("step-flow", "step-then", "step-else", "step-fork-branch", "step-contains"):
        for source, target in _edges(shape, conn_type):
            successors.setdefault(source, []).append(target)
    return successors


def _reachable_from(start: str, successors: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        step_id = queue.popleft()
        if step_id in seen:
            continue
        seen.add(step_id)
        queue.extend(successors.get(step_id, ()))
    return seen


def _arms(shape: ActivityShape, decision_id: str) -> list[str]:
    arms = [t for s, t in _edges(shape, "step-then") if s == decision_id]
    arms += [t for s, t in _edges(shape, "step-else") if s == decision_id]
    return arms


# ── the four assertions ──────────────────────────────────────────────────────


def _all_shapes() -> list[ActivityShape]:
    return [*CATALOGUE, *bundled_shapes()]


def _shape_ids() -> list[str]:
    return [shape.name for shape in _all_shapes()]


@pytest.fixture(params=_all_shapes(), ids=_shape_ids())
def shape(request: pytest.FixtureRequest) -> ActivityShape:
    return request.param


class TestEveryDeclaredStepIsDrawn:
    def test_coverage(self, shape: ActivityShape) -> None:
        """No reachability escape clause: a step the model declares is a step the picture owes."""
        body = shape.render()
        drawn = _drawn_steps(_parse(body))

        missing = [s for s in _declared(shape, _LABELLED_KINDS) if drawn.count(s) == 0]

        assert not missing, f"{shape.name}: declared but never drawn: {missing}\n{body}"

    def test_no_step_is_drawn_more_often_than_the_model_gives_it_ways_in(
        self, shape: ActivityShape
    ) -> None:
        """The bound on duplication, taken from the model rather than from the walk.

        A step two branches arrive at is drawn in both, because nothing structured covers exactly
        those two paths and a reader has to see that both paths reach it. What that must never become
        is the fork-multiplication defect, where a single tail with one way in appeared once per
        branch. So the ceiling is the number of edges the model points at the step.
        """
        body = shape.render()
        drawn = _drawn_steps(_parse(body))
        counted = {step_id: drawn.count(step_id) for step_id in set(drawn)}
        predecessors: dict[str, list[str]] = {}
        for conn_type in ("step-flow", "step-then", "step-else", "step-fork-branch", "step-contains"):
            for source, target in _edges(shape, conn_type):
                predecessors.setdefault(target, []).append(source)

        def ceiling(step_id: str) -> int:
            # A step that draws nothing — a join — still counts as one way in, so what follows it is
            # not held to a ceiling of zero.
            leading_in = predecessors.get(step_id) or []
            return max(1, sum(max(1, counted.get(source, 0)) for source in leading_in))

        over = {
            step_id: (count, ceiling(step_id))
            for step_id, count in counted.items()
            if count > ceiling(step_id)
        }

        assert not over, (
            f"{shape.name}: drawn more often than what leads to it: {over}\n{body}"
        )

    def test_every_drawing_of_a_step_is_the_step_itself(self, shape: ActivityShape) -> None:
        """Not a connector, not a jump. Both were tried and both are worse.

        `label` / `goto` is inert on the pinned PlantUML — a backward `goto` draws an arrow to the
        following node and inside a branch leaves a dangling arrowhead. A connector pair renders
        correctly and is unreadable here: an unlabelled circle in a viewer where every element is
        expected to be clickable and to resolve to the artifact it stands for.
        """
        body = shape.render()

        stubs = [
            line.strip() for line in body.splitlines()
            if line.strip().startswith(("goto ", "label ", "detach"))
            or (line.strip().startswith("(") and line.strip().endswith(")"))
        ]

        assert not stubs, f"{shape.name}: drawn as a stub rather than as the step: {stubs}\n{body}"


def _loop_conditions(tree: Node) -> set[str]:
    """The decisions drawn as a loop's condition rather than as an `if`.

    Such a decision has no arms to draw: one arm *is* the loop body, already drawn above the
    condition, and the other is the exit, drawn after it. So the arm-placement rule below does not
    apply to it, and the loop's own rule does.
    """
    found: set[str] = set()
    for region in tree.regions:
        for child in region.nodes:
            if child.kind == "loop":
                found |= {n.step_id for n in child.regions[-1].nodes if n.kind == "step" and n.step_id}
                # Only the last node of a loop is its condition; the rest are body steps.
                body_nodes = [n for n in child.regions[-1].nodes if n.kind == "step" and n.step_id]
                found = (found - {n.step_id for n in body_nodes[:-1] if n.step_id}) if body_nodes else found
            if child.kind in ("decision", "fork", "partition", "loop"):
                found |= _loop_conditions(child)
    return found


class TestABranchDrawsWhatItReaches:
    def test_a_decision_arm_reaches_its_first_step(self, shape: ActivityShape) -> None:
        """Inside the arm's own region, jumped to from it, or hoisted past this decision's endif.

        A decision drawn as a **loop condition** is exempt, and that is the loop's shape rather than a
        gap in it: the diamond sits at the foot of a `repeat`, one arm is the body above it and the
        other is the exit below, so there are no arm regions for a target to be inside.
        `TestALoopIsDrawnAsALoop` is where those two are asserted.
        """
        body = shape.render()
        tree = _parse(body)
        conditions = _loop_conditions(tree)

        labelled = set(_declared(shape, _LABELLED_KINDS))
        for arm_index, conn_type in ((0, "step-then"), (1, "step-else")):
            for decision_id, first in _edges(shape, conn_type):
                if first not in labelled or decision_id in conditions:
                    continue  # a fork or a join emits no labelled line, so its placement is unobservable
                found = _find_construct(tree, "decision", decision_id)
                assert found, f"{shape.name}: decision {decision_id} was not drawn\n{body}"
                node, holder = found
                assert arm_index < len(node.regions), f"{shape.name}: {decision_id} has no {conn_type} arm\n{body}"
                in_arm = first in _reached_in(node.regions[arm_index])
                hoisted = _step_after(holder, node) == first
                assert in_arm or hoisted, (
                    f"{shape.name}: {conn_type} {decision_id} -> {first}: the target is neither in "
                    f"that arm's region nor hoisted past its endif\n{body}"
                )

    def test_a_fork_branch_reaches_its_first_step(self, shape: ActivityShape) -> None:
        """A fork emits no sentinel, so its node is identified by the branches it holds."""
        body = shape.render()
        tree = _parse(body)
        by_fork: dict[str, list[str]] = {}
        for fork_id, first in _edges(shape, "step-fork-branch"):
            by_fork.setdefault(fork_id, []).append(first)

        labelled = set(_declared(shape, _LABELLED_KINDS))
        for fork_id, firsts in by_fork.items():
            placed = _forks_placing(tree, firsts, labelled)
            assert placed, (
                f"{shape.name}: fork {fork_id} has no emitted `fork` whose regions hold its "
                f"branches {firsts}\n{body}"
            )


class TestWhatFollowsAJoinIsDrawnWhereTheForkCloses:
    def test_the_join_continuation_sits_after_end_fork(self, shape: ActivityShape) -> None:
        """The join a branch reaches may be several constructs deep, and its continuation is the fork's.

        Coverage alone cannot see this: the pass over unemitted steps draws the continuation
        *somewhere*, so every step is present while the picture puts the tail outside the flow that
        leads to it. What the fork owes is that the tail sits immediately past its own `end fork`.
        """
        body = shape.render()
        tree = _parse(body)
        labelled = set(_declared(shape, _LABELLED_KINDS))
        successors = _successors(shape)
        joins = {
            step_id for step_id in _declared(shape, ("fork",))
            if not [t for s, t in _edges(shape, "step-fork-branch") if s == step_id]
        }

        for fork_id in _declared(shape, ("fork",)):
            firsts = [t for s, t in _edges(shape, "step-fork-branch") if s == fork_id]
            if not firsts:
                continue
            reached_joins = [j for j in joins if any(j in _reachable_from(f, successors) for f in firsts)]
            if not reached_joins:
                continue
            # Which of several reachable joins this fork closes on is the renderer's choice, and
            # restating it here would make the gate a copy of the walk. What is owed either way is
            # that the tail past `end fork` is the continuation of a join the branches do reach.
            continuations = {
                t for j in reached_joins for s, t in _edges(shape, "step-flow")
                if s == j and t in labelled
            }
            if not continuations:
                continue
            for node in _forks_placing(tree, firsts, labelled):
                holder = _region_holding(tree, node)
                assert holder is not None, f"{shape.name}: fork {fork_id} has no holding region\n{body}"
                assert _step_after(holder, node) in continuations, (
                    f"{shape.name}: fork {fork_id} reaches a join, so one of {sorted(continuations)} "
                    f"belongs past its `end fork`; what follows is "
                    f"{_step_after(holder, node)!r}\n{body}"
                )


def _region_holding(node: Node, wanted: Node) -> Region | None:
    for region in node.regions:
        if wanted in region.nodes:
            return region
        for child in region.nodes:
            if child.kind in ("decision", "fork", "partition"):
                found = _region_holding(child, wanted)
                if found is not None:
                    return found
    return None


class TestAConvergenceIsNotDrawnInsideOneArm:
    def test_a_step_every_arm_reaches_is_drawn_in_all_of_them_or_in_none(
        self, shape: ActivityShape
    ) -> None:
        """The defect this release exists for: the whole process drawn inside the first arm.

        A step every arm of a decision reaches belongs after that decision's `endif`, where one
        drawing serves both paths. Where nothing structured covers exactly those arrivals it is drawn
        in each arm that reaches it. What it must never be is drawn in *some* of them, which is a
        picture saying one path carries on and the other stops.
        """
        body = shape.render()
        tree = _parse(body)
        successors = _successors(shape)
        conditions = _loop_conditions(tree)

        for decision_id in _declared(shape, ("decision",)):
            arms = _arms(shape, decision_id)
            # A loop condition has no arm regions to compare — one arm is the body above it and the
            # other the exit below — so "drawn inside one arm and not the other" cannot arise.
            if len(arms) < 2 or decision_id in conditions:
                continue
            converging = set.intersection(*(_reachable_from(a, successors) for a in arms))
            found = _find_construct(tree, "decision", decision_id)
            assert found, f"{shape.name}: decision {decision_id} was not drawn\n{body}"
            node, _holder = found
            regions = node.regions[:len(arms)]
            for step_id in sorted(converging):
                drawing = [index for index, region in enumerate(regions) if step_id in _drawn_in(region)]

                assert len(drawing) in (0, len(regions)), (
                    f"{shape.name}: {step_id} is reached by every arm of {decision_id} but is drawn "
                    f"inside arm(s) {drawing} of {len(regions)}\n{body}"
                )


class TestALoopIsDrawnAsALoop:
    """What the two exemptions above are exempt *for*.

    A cycle used to close silently: the walk stopped at the returning step, nothing was drawn, and the
    picture said the flow fell straight through — the opposite of what the model declared, with every
    step present so coverage saw nothing wrong. So the properties worth asserting are the ones a
    silent close would fail.
    """

    def test_a_declared_cycle_is_drawn_as_a_repeat(self, shape: ActivityShape) -> None:
        body = shape.render()
        loops, _refused = cycles_of(_graph_of(shape), start=_root_of(shape))
        if not loops:
            return

        assert "repeat" in body, f"{shape.name}: a drawable loop was found and no repeat was drawn\n{body}"
        for loop in loops:
            assert "repeat while (" in body
            assert sentinel_in_repeat_while(body) == loop.condition, (
                f"{shape.name}: the repeat while draws {sentinel_in_repeat_while(body)!r} rather than "
                f"the loop's condition {loop.condition!r}\n{body}"
            )

    def test_the_body_precedes_the_condition_and_the_exit_follows_the_loop(
        self, shape: ActivityShape
    ) -> None:
        """The whole shape of a `repeat`: what runs each time is above the diamond, and what runs once
        the loop ends is below it. Reversing them is a picture that reads backwards."""
        body = shape.render()
        loops, _refused = cycles_of(_graph_of(shape), start=_root_of(shape))
        lines = body.splitlines()

        for loop in loops:
            condition_at = next(i for i, line in enumerate(lines) if line.startswith("repeat while ("))
            opened_at = next(i for i, line in enumerate(lines) if line.strip() == "repeat")
            for step_id in loop.body:
                drawn_at = next(
                    (i for i, line in enumerate(lines) if sentinel_of(line) == step_id), None
                )
                assert drawn_at is not None and opened_at < drawn_at < condition_at, (
                    f"{shape.name}: {step_id} runs each time round but is not drawn inside the "
                    f"repeat\n{body}"
                )
            if loop.exit_target:
                exit_at = next(
                    (i for i, line in enumerate(lines) if sentinel_of(line) == loop.exit_target), None
                )
                assert exit_at is None or exit_at > condition_at, (
                    f"{shape.name}: {loop.exit_target} runs when the loop ends but is drawn inside "
                    f"it\n{body}"
                )

    def test_a_step_on_the_way_back_is_drawn_backward(self, shape: ActivityShape) -> None:
        """`backward:` is what puts it on the returning arrow rather than in the forward chain, where
        it would read as running before the condition instead of after it."""
        body = shape.render()
        loops, _refused = cycles_of(_graph_of(shape), start=_root_of(shape))

        for loop in loops:
            for step_id in loop.backward:
                assert any(
                    line.startswith("backward:") and sentinel_of(line) == step_id
                    for line in body.splitlines()
                ), f"{shape.name}: {step_id} runs on the way back but is not drawn backward\n{body}"

    def test_the_condition_is_drawn_once(self, shape: ActivityShape) -> None:
        """It is consumed by the `repeat while` line. Drawing it as an `if` as well would put the same
        diamond in the picture twice — which the pass over unemitted steps would happily do."""
        body = shape.render()
        loops, _refused = cycles_of(_graph_of(shape), start=_root_of(shape))

        for loop in loops:
            drawn = [line for line in body.splitlines() if sentinel_of(line) == loop.condition]
            assert len(drawn) == 1, (
                f"{shape.name}: the loop condition {loop.condition} is drawn {len(drawn)} times\n{body}"
            )


def sentinel_in_repeat_while(body: str) -> str | None:
    return next(
        (sentinel_of(line) for line in body.splitlines() if line.startswith("repeat while (")), None
    )


def _graph_of(shape: ActivityShape) -> StepGraph:
    """The shape's declared graph, built the way the renderer builds it."""
    return StepGraph(
        step_by_id=_build_step_by_id(shape.entities),
        flow_next=_build_single_target(shape.connections, "step-flow"),
        then_target=_build_single_target(shape.connections, "step-then"),
        else_target=_build_single_target(shape.connections, "step-else"),
        fork_branches=_build_multi_target(shape.connections, "step-fork-branch"),
        contains_first=_build_single_target(shape.connections, "step-contains"),
    )


def _root_of(shape: ActivityShape) -> str | None:
    return _find_root(_graph_of(shape), _branch_owned_set(_graph_of(shape)))


def _drawn_in(region: Region) -> set[str]:
    return set(_drawn_steps(Node("root", None, [region])))


