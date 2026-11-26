"""A decision arm that returns to a step already drawn above it says where it returns to.

Such an arm is a back edge the notation cannot draw as an arrow outside a `repeat` — W048/W049 name it
and say why. The drawing was left with an empty arm, and an empty arm reads as a dead end: in a release
workflow, "Code change required? yes" led nowhere, where the model says it returns to development. The
verifier told the author; nothing told the reader.

The arm's label now carries the target, e.g. `(yes, back to develop)`. Only an arm whose first step is
one the walk is already inside — a step drawn above it on the same path. An arm that is empty because it
goes straight to the convergence point is a forward edge, drawn by the `endif`, and keeps its label.
"""

from __future__ import annotations

from src.diagram_types.activity._step_links import drawn_step_counts

from ._activity_shapes import (
    BOTH_ARMS_CONVERGE,
    ActivityShape,
    actions,
    decision,
    flow,
    otherwise,
    then,
)

# Two steps return to `dev` — the decision's yes-arm and the pipeline's last step — so no `repeat` can
# draw the cycle and the decision is drawn as an `if`.
TWO_RETURNS_TO_ONE_STEP = ActivityShape(
    name="two returns to one step",
    exercises="A decision arm that returns to the step before it, in a cycle a repeat cannot draw.",
    entities={
        "action": actions(dev="develop", pr="update the PR", vision="set the vision"),
        "decision": [decision("code", "code change required")],
    },
    connections=[
        flow("dev", "code"), then("code", "dev"), otherwise("code", "pr"),
        flow("pr", "vision"), flow("vision", "dev"),
    ],
)

# A decision whose arm returns to the decision itself.
AN_ARM_BACK_TO_ITS_OWN_DECISION = ActivityShape(
    name="an arm back to its own decision",
    exercises="The shortest back edge: an arm naming the decision it leaves.",
    entities={
        "action": actions(start_it="start it", finish="finish it", tidy="tidy up"),
        "decision": [decision("ready", "is it ready")],
    },
    connections=[
        flow("start_it", "ready"), then("ready", "finish"), otherwise("ready", "ready"),
        flow("finish", "tidy"), flow("tidy", "start_it"),
    ],
)


def _if_and_else(body: str) -> tuple[str, str]:
    lines = [line.strip() for line in body.splitlines()]
    return (next(line for line in lines if line.startswith("if (")),
            next(line for line in lines if line.startswith("else (")))


def test_the_arm_names_the_step_it_returns_to() -> None:
    opening, _ = _if_and_else(TWO_RETURNS_TO_ONE_STEP.render())

    assert opening.endswith("then (yes, back to develop)"), opening


def test_the_other_arm_keeps_its_label() -> None:
    _, otherwise_line = _if_and_else(TWO_RETURNS_TO_ONE_STEP.render())

    assert otherwise_line == "else (no)"


def test_an_arm_back_to_its_own_decision_names_the_question() -> None:
    _, otherwise_line = _if_and_else(AN_ARM_BACK_TO_ITS_OWN_DECISION.render())

    assert otherwise_line == "else (no, back to is it ready?)", otherwise_line


def test_the_annotation_draws_no_step() -> None:
    """The label is text, not a sentinel: W050 counts drawings by sentinel and must not see one more."""
    counts = drawn_step_counts(TWO_RETURNS_TO_ONE_STEP.render())

    assert counts["dev"] == 1


def test_an_arm_that_goes_forward_is_untouched() -> None:
    """Both arms converge on a step drawn after the `endif` — empty arms, not back edges."""
    opening, otherwise_line = _if_and_else(BOTH_ARMS_CONVERGE.render())

    assert "back to" not in opening and "back to" not in otherwise_line
