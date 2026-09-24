"""No two nodes of a GSN argument are drawn over each other, however many side nodes a rank carries.

A goal with two contexts, above a strategy with a justification, drew the second context under the
justification: side nodes stacked downward from their rank's centre line inside a band sized for the
rank's main row alone. The first real case with that shape — the rendering assurance case — showed it.
"""

from __future__ import annotations

from itertools import combinations

from src.diagram_types.gsn.svg_renderer import GsnEdge, GsnNode, PlacedNode, _place


def _node(alias: str, node_type: str, words: int = 12) -> GsnNode:
    return GsnNode(alias, node_type, tuple(f"{alias} line {i}" for i in range(max(1, words // 3))))


def _overlap(a: PlacedNode, b: PlacedNode) -> bool:
    return (
        abs(a.x - b.x) * 2 < a.width + b.width
        and abs(a.y - b.y) * 2 < a.height + b.height
    )


def test_two_contexts_on_a_goal_do_not_run_into_the_next_rank() -> None:
    nodes = [
        _node("g1", "goal"), _node("c1", "context", 15), _node("c2", "context", 15),
        _node("s1", "strategy"), _node("j1", "justification", 15),
        _node("g2", "goal"), _node("g3", "goal"), _node("a1", "assumption"),
        _node("sn1", "solution"), _node("sn2", "solution"),
    ]
    edges = [
        GsnEdge("g1", "s1", "supported-by"), GsnEdge("g1", "c1", "in-context-of"),
        GsnEdge("g1", "c2", "in-context-of"), GsnEdge("s1", "j1", "in-context-of"),
        GsnEdge("s1", "g2", "supported-by"), GsnEdge("s1", "g3", "supported-by"),
        GsnEdge("g3", "a1", "in-context-of"), GsnEdge("g2", "sn1", "supported-by"),
        GsnEdge("g3", "sn2", "supported-by"),
    ]

    placed, _, height = _place(nodes, edges)

    overlapping = [(a.node.alias, b.node.alias) for a, b in combinations(placed, 2) if _overlap(a, b)]
    assert overlapping == []
    assert all(item.y + item.height / 2 <= height for item in placed)


def test_a_side_node_still_sits_beside_the_node_it_qualifies() -> None:
    nodes = [_node("g1", "goal"), _node("c1", "context"), _node("sn1", "solution")]
    edges = [GsnEdge("g1", "c1", "in-context-of"), GsnEdge("g1", "sn1", "supported-by")]

    placed = {item.node.alias: item for item in _place(nodes, edges)[0]}

    goal, context, solution = placed["g1"], placed["c1"], placed["sn1"]
    assert context.x > goal.x
    assert context.y - context.height / 2 < goal.y + goal.height / 2 < solution.y


def test_a_side_node_s_connector_crosses_no_other_node_of_its_rank() -> None:
    """An assumption qualifying the middle goal of three was joined by a line drawn through the goal to
    its right, so it read as that goal's assumption."""
    nodes = [
        _node("s1", "strategy"), _node("g1", "goal"), _node("g2", "goal"), _node("g3", "goal"),
        _node("a1", "assumption"),
    ]
    edges = [
        GsnEdge("s1", "g1", "supported-by"), GsnEdge("s1", "g2", "supported-by"),
        GsnEdge("s1", "g3", "supported-by"), GsnEdge("g2", "a1", "in-context-of"),
    ]

    placed = {item.node.alias: item for item in _place(nodes, edges)[0]}

    qualified, side = placed["g2"], placed["a1"]
    left, right = qualified.x + qualified.width / 2, side.x - side.width / 2
    for other in ("g1", "g3"):
        box = placed[other]
        spans_connector = box.x - box.width / 2 < right and box.x + box.width / 2 > left
        spans_height = abs(box.y - qualified.y) * 2 < box.height + qualified.height
        assert not (spans_connector and spans_height), f"the connector to {side.node.alias} crosses {other}"
