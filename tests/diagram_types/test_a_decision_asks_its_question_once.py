"""A decision's diamond asks its question with exactly one question mark (B87).

The emitter appended `?` to every condition. A condition authored as a question — "does the model
already hold this?" — rendered "…this??", which three decisions in a published diagram showed; a
decision with no condition rendered "??". Conditions are written both ways, so the mark is added only
where the text does not already end in one — for an `if` and for the foot of a loop alike.
"""

from __future__ import annotations

import re

import pytest

from tests.diagram_types._activity_shapes import (
    ActivityShape,
    actions,
    decision,
    flow,
    otherwise,
    then,
)


def _branch(condition: str) -> ActivityShape:
    return ActivityShape(
        name="one decision", exercises="a branch",
        entities={"action": actions(a="go", b="stop"), "decision": [decision("d", condition)]},
        connections=[then("d", "a"), otherwise("d", "b")],
    )


def _loop(condition: str) -> ActivityShape:
    return ActivityShape(
        name="one loop", exercises="a retry loop",
        entities={
            "action": actions(attempt="attempt the write", wait="back off", accept="accept it"),
            "decision": [decision("ok", condition)],
        },
        connections=[flow("attempt", "ok"), then("ok", "accept"), otherwise("ok", "wait"), flow("wait", "attempt")],
    )


def _asked(body: str, keyword: str) -> list[str]:
    """The text inside every `if (...)` or `repeat while (...)` the body emits, link sentinels removed."""
    found = re.findall(rf"^{keyword} \((.*?)\)(?: then| is)", body, flags=re.MULTILINE)
    return [re.sub(r"\[\[arch://\S+ (.*?)\]\]", r"\1", text) for text in found]


@pytest.mark.parametrize("condition", ["does it pass?", "does it pass", "does it pass? "])
def test_a_branch_asks_once_however_the_condition_was_written(condition: str) -> None:
    assert _asked(_branch(condition).render(), "if") == ["does it pass?"]


def test_a_branch_with_no_condition_asks_a_single_mark() -> None:
    assert _asked(_branch("").render(), "if") == ["?"]


@pytest.mark.parametrize("condition", ["did it succeed?", "did it succeed"])
def test_the_foot_of_a_loop_asks_once_too(condition: str) -> None:
    assert _asked(_loop(condition).render(), "repeat while") == ["did it succeed?"]
