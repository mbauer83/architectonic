"""A drawn loop opens in the lane its steps run in, not in whichever lane the walk was in before it.

`repeat` draws the loop's entry point: the diamond a returning flow comes back to. It was emitted before
the walk into the loop's header, and the header's lane switch is part of that walk, so a loop confined to
one lane opened its entry point in the lane *before* it. The picture connected, and it put the top of
the loop under the wrong performer.

A drawn loop is always confined to one lane — `_step_cycles` refuses one that crosses a lane — so "the
loop's lane" is well defined: it is the header's.

Stated over every catalogue shape that declares lanes and draws a loop, rather than over the one shape
that showed it.
"""

from __future__ import annotations

import pytest

from src.diagram_types.activity._step_links import _is_lane_header, sentinel_of

from ._activity_shapes import (
    A_FORK_INSIDE_A_LOOP_BODY,
    A_LOOP_WHOSE_BODY_HOLDS_A_DECISION,
    ActivityShape,
    actions,
    decision,
    flow,
    in_lane,
    otherwise,
    then,
)

# The loop is entered from a step in a different lane, which is what puts the walk in the wrong lane
# at the moment `repeat` is written. The two catalogue shapes above cover a body holding a decision and
# a body holding a fork; this one is the plainest loop there is.
A_PLAIN_LOOP_ENTERED_FROM_ANOTHER_LANE = ActivityShape(
    name="a plain loop entered from another lane",
    exercises="A one-step loop body in one lane, entered from a step in the other lane.",
    entities={
        "action": actions(ask="ask for it", poll="poll the job", hand="hand it over"),
        "decision": [decision("done", "is it done")],
        "swimlane": [{"id": "lane_caller", "label": "Caller"},
                     {"id": "lane_service", "label": "Service"}],
    },
    connections=[
        flow("ask", "poll"), flow("poll", "done"),
        then("done", "hand"), otherwise("done", "poll"),
        in_lane("ask", "lane_caller"), in_lane("hand", "lane_caller"),
        in_lane("poll", "lane_service"), in_lane("done", "lane_service"),
    ],
)

_SHAPES = [A_LOOP_WHOSE_BODY_HOLDS_A_DECISION, A_FORK_INSIDE_A_LOOP_BODY,
           A_PLAIN_LOOP_ENTERED_FROM_ANOTHER_LANE]


def _lane_of(shape: ActivityShape, step_id: str) -> str:
    return next(str(c["target"]) for c in shape.connections
                if c["conn_type"] == "step-in-lane" and c["source"] == step_id)


def _lanes_at_each_repeat(body: str) -> list[tuple[str | None, str | None]]:
    """For each `repeat`, the lane in force where it is written and the step drawn right after it."""
    current: str | None = None
    found: list[tuple[str | None, str | None]] = []
    lines = [line.strip() for line in body.splitlines()]
    for index, line in enumerate(lines):
        if _is_lane_header(line):
            current = sentinel_of(line)
        elif line == "repeat":
            following = next((sentinel_of(later) for later in lines[index + 1:]
                              if sentinel_of(later) and not _is_lane_header(later)), None)
            found.append((current, following))
    return found


@pytest.mark.parametrize("shape", _SHAPES, ids=lambda s: s.name)
def test_the_loop_opens_in_its_header_lane(shape: ActivityShape) -> None:
    repeats = _lanes_at_each_repeat(shape.render())

    assert repeats, f"{shape.name} draws no loop, so it says nothing about where one opens"
    for lane, header in repeats:
        assert header is not None
        assert lane == _lane_of(shape, header), (
            f"the loop headed by {header!r} opens in {lane!r}, not in its own lane"
        )


def test_the_lane_is_not_switched_twice() -> None:
    """Entering the lane before `repeat` must not leave the header's own switch to repeat it."""
    body = A_PLAIN_LOOP_ENTERED_FROM_ANOTHER_LANE.render()

    headers = [line.strip() for line in body.splitlines() if _is_lane_header(line)]
    assert [sentinel_of(h) for h in headers] == ["lane_caller", "lane_service", "lane_caller"]
