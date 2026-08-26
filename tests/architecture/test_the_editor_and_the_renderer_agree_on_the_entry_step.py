"""Which step leads an activity diagram: one rule, two languages, checked against one table.

The server half of a cross-language conformance pair. The browser half is
`tools/gui/src/ui/diagram-types/activity/__tests__/activityStepGraph.test.ts`, whose `ROOT_SAMPLES`
holds these same graphs and asserts its outline leads with the same step.

**Why there are two implementations at all.** The editor rebuilds its outline synchronously on every
keystroke over state that has not been saved, so it cannot ask the server; and the answer decides what
an author sees and edits, while the same answer decides what the renderer draws. A diagram whose
outline disagrees with its picture is worse than either being wrong alone, because the author works on
one and looks at the other.

**What the disagreement cost, measured before this was written.** The editor had only the first of the
server's three tiers — a step nothing flows into and no branch owns. Every step of a cycle is reached
from somewhere, so on a diagram that is entirely a retry loop that tier finds nothing, and the fallback
listed the steps no branch owns, which for such a graph is none of them. The editor showed an empty
outline for a diagram the renderer draws in full, and saving it would have written the steps away.

The way to hold two languages to one convention is to write down what it produces and check both sides
against it — the same device `test_every_style_token_has_a_colour` uses for the ramp. If a sample
changes here it must change there in the same commit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.diagram_types.activity._step_graph import entry_step, graph_from_declarations

_BROWSER_HALF = (
    Path(__file__).resolve().parents[2]
    / "tools" / "gui" / "src" / "ui" / "diagram-types" / "activity"
    / "__tests__" / "activityStepGraph.test.ts"
)


def _step(step_id: str, kind: str = "action") -> dict[str, str]:
    return {"id": step_id, "type": kind, "label": step_id}


def _edge(conn_type: str, source: str, target: str) -> dict[str, str]:
    return {"conn_type": conn_type, "source": source, "target": target}


#: `(name, diagram-entities, connections, the step that leads)`.
ROOT_SAMPLES: tuple[tuple[str, dict[str, object], list[dict[str, str]], str], ...] = (
    (
        "a plain chain leads with the step nothing flows into",
        {"action": [_step("a1"), _step("a2")]},
        [_edge("step-flow", "a1", "a2")],
        "a1",
    ),
    (
        "a decision does not make its own branches candidates",
        {"action": [_step("start"), _step("yes"), _step("no")], "decision": [_step("d", "decision")]},
        [
            _edge("step-flow", "start", "d"),
            _edge("step-then", "d", "yes"),
            _edge("step-else", "d", "no"),
        ],
        "start",
    ),
    (
        "a retry loop entered from outside still leads with the step outside it",
        {
            "action": [_step("start"), _step("attempt"), _step("wait"), _step("done")],
            "decision": [_step("ok", "decision")],
        },
        [
            _edge("step-flow", "start", "attempt"),
            _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"),
            _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"),
        ],
        "start",
    ),
    (
        "a diagram that is nothing but a loop leads with a step no branch enters",
        {
            "action": [_step("attempt"), _step("wait"), _step("done")],
            "decision": [_step("ok", "decision")],
        },
        [
            _edge("step-flow", "attempt", "ok"),
            _edge("step-then", "ok", "done"),
            _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"),
        ],
        "attempt",
    ),
    (
        "a closed ring leads with the first declared step",
        {"action": [_step("a"), _step("b")]},
        [_edge("step-flow", "a", "b"), _edge("step-flow", "b", "a")],
        "a",
    ),
)


@pytest.mark.parametrize(("name", "entities", "connections", "expected"), ROOT_SAMPLES)
def test_the_server_leads_with_the_step_the_table_names(
    name: str, entities: dict[str, object], connections: list[dict[str, str]], expected: str
) -> None:
    del name
    assert entry_step(graph_from_declarations(entities, connections)) == expected


def test_the_browser_half_states_the_same_samples() -> None:
    """The table is only a convention if both sides carry it.

    Compared by the `(name, root)` pairs rather than by the whole graph literal: the two languages
    spell a step differently and always will, while the name says which case it is and the root says
    what the case asserts. A sample added on one side alone fails here, which is the point — the
    browser half cannot be run from this suite, and CI runs them in separate jobs.
    """
    source = _BROWSER_HALF.read_text(encoding="utf-8")
    found = re.findall(r"name:\s*'([^']+)',.*?root:\s*(?:'([^']*)'|null),", source, re.S)

    assert [(name, root) for name, root, in found] == [
        (name, expected) for name, _entities, _connections, expected in ROOT_SAMPLES
    ], "the two halves of the conformance table have parted; change both in one commit"


def test_the_samples_are_stated_over_data_both_sides_can_read() -> None:
    """Each sample is plain JSON — no Python object survives into the browser half, so a sample that
    could not be written there is caught here rather than by a reviewer."""
    for name, entities, connections, _expected in ROOT_SAMPLES:
        json.dumps({"name": name, "entities": entities, "connections": connections})
