"""Every step the model declares is drawn exactly once, in the branch that reaches it.

Four assertions, stated over the shapes the notation permits rather than over the shape that
broke. The order they are written in is the order they were *measured* in, and it matters:

* **Coverage** — every declared step appears exactly once. Blind on its own: the bundled diagram
  drew all thirteen of its steps exactly once while telling a reader that nothing happens when the
  two ends are not yet typed.
* **No repetition** — an upper bound over all steps. Subsumed by "exactly once", kept separate
  because the two fail differently: a fork that multiplies its tail should say "drawn twice", not
  "coverage wrong".
* **Per-branch coverage** — the one that goes red on the bundled diagram. A branch's first step is
  drawn inside that branch's own region, reached from it by a connector, or hoisted past the
  construct's own `endif`/`end fork` because every arm converges on it.
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

from src.diagram_types.activity._step_links import sentinel_of
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
    """The emitted body as a tree of regions.

    A connector pair is read as one node per half: the entry half sits immediately before the step
    it introduces, so the mark is resolved to that step and the arrival half is a jump to it.
    """
    marks: dict[str, str] = {}
    pending_mark: str | None = None
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("(") and line.endswith(")"):
            pending_mark = line[1:-1]
        elif pending_mark is not None and line.startswith((":", "if (", "partition ")):
            # A lane switch or a note may sit between the connector and the step it introduces.
            step_id = sentinel_of(line)
            if step_id:
                marks.setdefault(pending_mark, step_id)
            pending_mark = None
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
        elif line.startswith("(") and line.endswith(")"):
            stack[-1].regions[-1].nodes.append(Node("connector", marks.get(line[1:-1])))
        elif line == "detach":
            continue
        elif line.startswith(":") and line.endswith(";"):
            stack[-1].regions[-1].nodes.append(Node("step", sentinel_of(line)))
    return root


def _drawn_steps(node: Node) -> list[str]:
    """Every step id the body *draws*, in emission order. A connector draws nothing itself."""
    found: list[str] = []
    for region in node.regions:
        for child in region.nodes:
            if child.kind in ("decision", "partition") and child.step_id:
                found.append(child.step_id)
            if child.kind == "step" and child.step_id:
                found.append(child.step_id)
            elif child.kind in ("decision", "fork", "partition"):
                found.extend(_drawn_steps(child))
    return found


def _reached_in(region: Region) -> set[str]:
    """The steps this region draws or jumps to, at any depth inside it."""
    reached: set[str] = set()
    for child in region.nodes:
        if child.step_id and child.kind in ("step", "connector", "decision", "partition"):
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
        if following.kind == "connector":
            continue
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


class TestEveryDeclaredStepIsDrawnExactlyOnce:
    def test_coverage(self, shape: ActivityShape) -> None:
        """No reachability escape clause: a step the model declares is a step the picture owes."""
        body = shape.render()
        drawn = _drawn_steps(_parse(body))

        missing = [s for s in _declared(shape, _LABELLED_KINDS) if drawn.count(s) == 0]

        assert not missing, f"{shape.name}: declared but never drawn: {missing}\n{body}"

    def test_no_step_is_drawn_twice(self, shape: ActivityShape) -> None:
        """An upper bound over *all* steps — a defect-8 regression should say `drawn twice`."""
        body = shape.render()
        drawn = _drawn_steps(_parse(body))

        repeated = {s: drawn.count(s) for s in set(drawn) if drawn.count(s) > 1}

        assert not repeated, f"{shape.name}: drawn more than once: {repeated}\n{body}"


class TestABranchDrawsWhatItReaches:
    def test_a_decision_arm_reaches_its_first_step(self, shape: ActivityShape) -> None:
        """Inside the arm's own region, jumped to from it, or hoisted past this decision's endif."""
        body = shape.render()
        tree = _parse(body)

        labelled = set(_declared(shape, _LABELLED_KINDS))
        for arm_index, conn_type in ((0, "step-then"), (1, "step-else")):
            for decision_id, first in _edges(shape, conn_type):
                if first not in labelled:
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
    def test_a_step_every_arm_reaches_is_not_buried_in_one_of_them(self, shape: ActivityShape) -> None:
        """The defect this release exists for: the whole process drawn inside the first arm.

        A step that every arm of a decision reaches belongs after that decision's `endif`. Where the
        arrival points sit at different nesting depths and no single placement covers them, the
        others reach it by a connector — so an arm that connects to it is not "burying" it.
        """
        body = shape.render()
        tree = _parse(body)
        successors = _successors(shape)

        for decision_id in _declared(shape, ("decision",)):
            arms = _arms(shape, decision_id)
            if len(arms) < 2:
                continue
            converging = set.intersection(*(_reachable_from(a, successors) for a in arms))
            found = _find_construct(tree, "decision", decision_id)
            assert found, f"{shape.name}: decision {decision_id} was not drawn\n{body}"
            node, _holder = found
            regions = node.regions[:len(arms)]
            for step_id in sorted(converging):
                drawing = [i for i, r in enumerate(regions) if step_id in _drawn_in(r)]
                if not drawing:
                    continue
                jumping = [i for i, r in enumerate(regions) if _jumps_to(r, step_id)]
                assert len(drawing) + len(jumping) >= len(arms), (
                    f"{shape.name}: {step_id} is reached by every arm of {decision_id} but is drawn "
                    f"inside arm(s) {drawing} with no jump from the rest\n{body}"
                )


def _drawn_in(region: Region) -> set[str]:
    return set(_drawn_steps(Node("root", None, [region])))


def _jumps_to(region: Region, step_id: str) -> bool:
    for child in region.nodes:
        if child.kind == "connector" and child.step_id == step_id:
            return True
        if child.kind in ("decision", "fork", "partition") and any(
            _jumps_to(inner, step_id) for inner in child.regions
        ):
            return True
    return False
