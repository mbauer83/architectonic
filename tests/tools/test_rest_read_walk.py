"""The read walk runs, and it covers only reads.

The counterpart of `test_rest_write_walk.py`, and the mirror of the constraint that made this walk exist:
`test_the_write_walk_covers_only_write_shaped_operations` refuses reads in the write walk, so the reads
that nothing drives need somewhere of their own. This asserts the same discipline in the other direction —
a *write* appearing here would be the same quiet reclassification, just reversed.

`_walked_by_a_fixture_walk` in `tests/architecture/test_never_requested_operations.py` subtracts these
step ids from the dark set, which is a *claim*. The green run below is the evidence: every declared read
appears in the fixture backend's own log, so a step that stops being requested fails here rather than
silently exempting an operation there.
"""

from __future__ import annotations

import pytest

from src.infrastructure.rest.route_policy import BY_OPERATION
from tools.quality.fixture_backend import fixture_backend
from tools.quality.rest_read_walk import READ_STEPS, reached_operations, walk


def test_every_step_names_a_declared_operation() -> None:
    """A typo would exempt nothing from the register while looking like it exempted something."""
    unknown = sorted({step.operation_id for step in READ_STEPS} - set(BY_OPERATION))
    assert unknown == [], unknown


def test_the_walk_covers_only_read_shaped_operations() -> None:
    """The mirror of the write walk's guard, and the reason this file exists at all.

    A write here would measure the write surface with a read harness — the same conflation, reversed, and
    just as effective at making a register unable to answer its own question.
    """
    writes = sorted(
        step.operation_id for step in READ_STEPS if BY_OPERATION[step.operation_id].method != "GET"
    )
    assert writes == [], writes


def test_every_step_says_why_nothing_else_reaches_it() -> None:
    """These five are dark because no *client* drives them, which is a claim about the product.

    So each carries the reason, the walk prints it, and a reader deciding whether to retire a route gets
    the argument rather than a bare operation id. Length-checked because a one-word reason is one nobody
    can act on — the same rule the other registers' reasons are held to.
    """
    for step in READ_STEPS:
        assert len(step.because) > 30, (step.operation_id, step.because)


def test_no_step_is_also_walked_by_the_write_walks() -> None:
    """Two walks requesting one operation would make either one's failure invisible in the register.

    The subtraction is a union, so an operation in both sets is exempted by whichever runs — and the walk
    that stopped covering it would fail its own test while the register stayed quiet.
    """
    from tools.quality.rest_write_walk import ADMIN_STEPS, STEPS

    written = {step.operation_id for step in (*STEPS, *ADMIN_STEPS)}
    overlap = sorted({step.operation_id for step in READ_STEPS} & written)
    assert overlap == [], overlap


@pytest.mark.slow_walk
def test_the_walk_runs_green_against_a_fixture_backend() -> None:
    """Every declared read answers 200, and the server's own log says it was asked.

    The log is the measurement; the step list is only the intention. That distinction is why the register
    can subtract these ids at all — see `_walked_by_a_fixture_walk`.
    """
    with fixture_backend() as backend:
        answered, failures = walk(backend)
        reached = reached_operations(backend)

    assert failures == [], failures
    expected = {step.operation_id for step in READ_STEPS}
    assert set(answered) == expected, sorted(expected - set(answered))
    assert expected <= reached, sorted(expected - reached)
