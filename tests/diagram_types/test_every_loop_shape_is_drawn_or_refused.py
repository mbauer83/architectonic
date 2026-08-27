"""The shape matrix: for every loop and convergence shape, what the product does with it.

**This is the gate that was missing**, and its absence is why v0.8.0 shipped a loop feature that was
unsound for ordinary shapes. The feature's own test asserted `== []` for the drawable case — a form
that passes both when a loop is drawn correctly *and* when no cycle is detected at all — so three
shapes were neither drawn nor refused and the suite was green.

Every row here asserts the **positive** fact. A shape is drawn, or it is refused with a reason; never
"nothing was reported".

The shapes were chosen by working outwards from the one the feature was built for, and each row names
what it exercises. Where the answer is "refused", that is a statement about `repeat`'s expressivity and
not a defect: a structured `repeat` shows one header, one body chain, one condition and one returning
step, and a cycle carrying more than that has no faithful rendering in this notation. What matters is
that the product says so instead of drawing a picture the model does not describe.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.diagram_types.activity._step_cycles import cycles_of
from src.diagram_types.activity._step_graph import entry_step, graph_from_declarations, lane_of_step


def _step(step_id: str, kind: str = "action") -> dict[str, Any]:
    step: dict[str, Any] = {"id": step_id, "type": kind, "label": step_id}
    if kind == "decision":
        step |= {"condition": f"{step_id}?", "then_label": "y", "else_label": "n"}
    return step


def _edge(conn_type: str, source: str, target: str) -> dict[str, str]:
    return {"id": f"{source}|{target}|{conn_type}", "conn_type": conn_type,
            "source": source, "target": target}


def _declare(actions: tuple[str, ...] = (), decisions: tuple[str, ...] = (),
             edges: tuple[dict[str, str], ...] = (),
             lanes: tuple[str, ...] = (),
             forks: tuple[str, ...] = ()) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """The declarations for one shape. *lanes* names the swimlanes; a step's lane is declared by a
    `step-in-lane` edge in *edges*, like any other placement."""
    entities: dict[str, Any] = {
        "action": [_step(i) for i in actions],
        "decision": [_step(i, "decision") for i in decisions],
    }
    if lanes:
        entities["swimlane"] = [{"id": i, "label": i} for i in lanes]
    if forks:
        entities["fork"] = [{"id": i} for i in forks]
    return (entities, list(edges))


#: `(name, exercises, declarations, expected)` where expected is `"drawn"` or `"refused"`.
SHAPES: tuple[tuple[str, str, tuple[dict[str, Any], list[dict[str, str]]], str], ...] = (
    (
        "one step on the way back",
        "the shape the feature exists for: a retry with one back-off step",
        _declare(("start", "attempt", "wait", "done"), ("ok",), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"))),
        "drawn",
    ),
    (
        "an arm pointing straight back",
        "no step on the way back at all — the condition returns to the header directly",
        _declare(("start", "attempt", "done"), ("ok",), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "attempt"))),
        "drawn",
    ),
    (
        "a self-loop",
        "the poll-until shape: one step and a condition that repeats it",
        _declare(("start", "poll", "done"), ("ok",), (
            _edge("step-flow", "start", "poll"), _edge("step-flow", "poll", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "poll"))),
        "drawn",
    ),
    (
        "two steps on the way back",
        "PlantUML draws one `backward:` activity and discards the rest — measured",
        _declare(("start", "attempt", "log", "wait", "done"), ("ok",), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"), _edge("step-flow", "wait", "attempt"))),
        "refused",
    ),
    (
        "a cycle with no decision in it",
        "nothing chooses whether to go round again, so there is no condition to draw",
        _declare(("start", "a1", "a2", "a3"), (), (
            _edge("step-flow", "start", "a1"), _edge("step-flow", "a1", "a2"),
            _edge("step-flow", "a2", "a3"), _edge("step-flow", "a3", "a1"))),
        "refused",
    ),
    (
        "a return declared as the decision's merge edge",
        "invisible to the cycle finder until it followed merge edges; drew an empty arm",
        _declare(("start", "a1", "a2", "done"), ("d1",), (
            _edge("step-flow", "start", "a1"), _edge("step-flow", "a1", "d1"),
            _edge("step-then", "d1", "a2"), _edge("step-flow", "d1", "a1"),
            _edge("step-flow", "a2", "done"))),
        "refused",
    ),
    (
        "two decisions returning to one header",
        "a repeat has one condition and one return; this was claimed drawable and drawn wrong",
        _declare(("start", "attempt", "w1", "w2", "done"), ("d1", "d2"), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "d1"),
            _edge("step-then", "d1", "d2"), _edge("step-else", "d1", "w1"),
            _edge("step-flow", "w1", "attempt"),
            _edge("step-then", "d2", "done"), _edge("step-else", "d2", "w2"),
            _edge("step-flow", "w2", "attempt"))),
        "refused",
    ),
    (
        "a loop whose body holds a decision",
        "the ordinary retry shape. Refused until the criterion described the region the emitter "
        "walks rather than a single-successor chain; PlantUML draws it correctly",
        _declare(("start", "attempt", "fix", "skip", "wait", "done"), ("inner", "ok"), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "inner"),
            _edge("step-then", "inner", "fix"), _edge("step-else", "inner", "skip"),
            _edge("step-flow", "inner", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"))),
        "drawn",
    ),
    (
        "a loop whose body holds a decision, all of it in one lane",
        "the same shape with lanes declared: confined to one lane it still draws",
        _declare(("start", "attempt", "fix", "skip", "wait", "done"), ("inner", "ok"), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "inner"),
            _edge("step-then", "inner", "fix"), _edge("step-else", "inner", "skip"),
            _edge("step-flow", "inner", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"),
            _edge("step-in-lane", "start", "lane_a"), _edge("step-in-lane", "done", "lane_a"),
            _edge("step-in-lane", "attempt", "lane_b"), _edge("step-in-lane", "inner", "lane_b"),
            _edge("step-in-lane", "fix", "lane_b"), _edge("step-in-lane", "skip", "lane_b"),
            _edge("step-in-lane", "ok", "lane_b"), _edge("step-in-lane", "wait", "lane_b")),
            lanes=("lane_a", "lane_b")),
        "drawn",
    ),
    (
        "a loop inside a loop",
        "two nested loops are ONE strongly connected component, so every step is accounted for "
        "inside the outer shape and the inner way back is drawn nowhere. Found by auditing what the "
        "region-walk criterion newly accepted, not by a failing test",
        _declare(("start", "outer", "inner_a", "wait_i", "wait_o", "done"), ("ci", "co"), (
            _edge("step-flow", "start", "outer"), _edge("step-flow", "outer", "inner_a"),
            _edge("step-flow", "inner_a", "ci"),
            _edge("step-else", "ci", "wait_i"), _edge("step-flow", "wait_i", "inner_a"),
            _edge("step-then", "ci", "co"),
            _edge("step-then", "co", "done"), _edge("step-else", "co", "wait_o"),
            _edge("step-flow", "wait_o", "outer"))),
        "refused",
    ),
    (
        "a body arm reaching the step after the loop",
        "the region walk follows the arm out and draws what comes after the loop inside it, so the "
        "picture runs those steps on every pass and shows no exit. Also found by audit",
        _declare(("start", "attempt", "fix", "bail", "wait", "done"), ("inner", "ok"), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "inner"),
            _edge("step-then", "inner", "fix"), _edge("step-else", "inner", "bail"),
            _edge("step-flow", "inner", "ok"), _edge("step-flow", "bail", "done"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"))),
        "refused",
    ),
    (
        "a fork inside a loop body",
        "the body region may hold any structured construct, not only a decision",
        _declare(("start", "attempt", "p1", "p2", "wait", "done"), ("ok",), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "split"),
            _edge("step-fork-branch", "split", "p1"), _edge("step-fork-branch", "split", "p2"),
            _edge("step-flow", "p1", "ok"), _edge("step-flow", "p2", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt")), forks=("split",)),
        "drawn",
    ),
    (
        "a loop spanning two swimlanes",
        "measured: a repeat crossing a lane draws its way back through the boxes it returns past, "
        "terminating inside the header instead of at its edge. The same shape in one lane is clean",
        _declare(("start", "attempt", "wait", "done"), ("ok",), (
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"),
            _edge("step-in-lane", "start", "lane_a"), _edge("step-in-lane", "attempt", "lane_a"),
            _edge("step-in-lane", "ok", "lane_b"), _edge("step-in-lane", "wait", "lane_a"),
            _edge("step-in-lane", "done", "lane_b")),
            lanes=("lane_a", "lane_b")),
        "refused",
    ),
)

#: Shapes that hold no cycle at all, so the cycle finder must say nothing about them. Kept in the
#: matrix because "no cycle" and "a cycle nobody saw" were indistinguishable before, and a convergence
#: mistaken for a cycle would refuse a correct diagram.
ACYCLIC: tuple[tuple[str, tuple[dict[str, Any], list[dict[str, str]]]], ...] = (
    (
        "two arms converge on a later step",
        _declare(("start", "yes1", "no1", "after"), ("d1",), (
            _edge("step-flow", "start", "d1"), _edge("step-then", "d1", "yes1"),
            _edge("step-else", "d1", "no1"), _edge("step-flow", "d1", "after"),
            _edge("step-flow", "yes1", "after"), _edge("step-flow", "no1", "after"))),
    ),
    (
        "three arms converge on one action",
        _declare(("start", "a1", "a2", "a3", "shared", "done"), ("d1", "d2", "d3"), (
            _edge("step-flow", "start", "a1"), _edge("step-flow", "a1", "d1"),
            _edge("step-then", "d1", "a2"), _edge("step-else", "d1", "shared"),
            _edge("step-flow", "a2", "d2"), _edge("step-then", "d2", "a3"),
            _edge("step-else", "d2", "shared"),
            _edge("step-flow", "a3", "d3"), _edge("step-then", "d3", "done"),
            _edge("step-else", "d3", "shared"))),
    ),
)


def _outcome(declarations: tuple[dict[str, Any], list[dict[str, str]]]) -> tuple[int, int]:
    entities, connections = declarations
    graph = graph_from_declarations(entities, connections)
    loops, refused = cycles_of(graph, lane_of_step(connections), start=entry_step(graph))
    return len(loops), len(refused)


@pytest.mark.parametrize(("name", "exercises", "declarations", "expected"), SHAPES)
def test_every_cycle_is_drawn_or_refused(
    name: str, exercises: str, declarations: tuple[dict[str, Any], list[dict[str, str]]],
    expected: str,
) -> None:
    del exercises
    drawn, refused = _outcome(declarations)

    assert drawn + refused == 1, f"{name}: the cycle was neither drawn nor refused"
    assert (drawn, refused) == ((1, 0) if expected == "drawn" else (0, 1)), (
        f"{name}: expected {expected}, got drawn={drawn} refused={refused}"
    )


@pytest.mark.parametrize(("name", "exercises", "declarations", "expected"), SHAPES)
def test_a_refusal_says_why(
    name: str, exercises: str, declarations: tuple[dict[str, Any], list[dict[str, str]]],
    expected: str,
) -> None:
    """A refusal with no reason is a shape an author cannot act on."""
    del exercises
    if expected != "refused":
        pytest.skip("this shape is drawn")
    entities, connections = declarations
    graph = graph_from_declarations(entities, connections)
    _loops, refused = cycles_of(graph, lane_of_step(connections), start=entry_step(graph))

    assert refused[0].reason.strip(), name
    assert refused[0].steps, f"{name}: a refusal names the steps it is about"


@pytest.mark.parametrize(("name", "declarations"), ACYCLIC)
def test_a_convergence_is_not_a_cycle(
    name: str, declarations: tuple[dict[str, Any], list[dict[str, str]]]
) -> None:
    assert _outcome(declarations) == (0, 0), f"{name}: reported as a cycle"
