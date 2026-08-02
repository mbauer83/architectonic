"""The REST write walk runs, and what it finds stays found.

The walk itself is the oracle; this is what keeps it honest in the suite. Three properties matter.

**It runs green** — every step answers as declared, against a real backend serving disposable content.

**Its registers are shrink-only and disjoint.** `UNWALKED` holds preconditions the fixture does not
build; `KNOWN_DEFECTS` holds operations it reaches and finds broken. An operation must not be in both,
and a defect must not be quietly reclassified as a precondition, because that is how a found bug turns
back into an unknown.

**A fixed defect fails this test.** `KNOWN_DEFECTS` pins the wrong answer, so repairing
`groups_delete_group` makes its step's `expect=(500,)` wrong and the walk red — which is the signal to
remove the entry, not a nuisance. A register that only ever describes is a register nobody updates.
"""

from __future__ import annotations

import pytest

from tools.quality.fixture_backend import fixture_backend
from tools.quality.rest_write_walk import KNOWN_DEFECTS, STEPS, UNWALKED, reached_operations, walk


def test_the_registers_are_disjoint_and_reasoned() -> None:
    assert not set(UNWALKED) & set(KNOWN_DEFECTS), set(UNWALKED) & set(KNOWN_DEFECTS)
    for register in (UNWALKED, KNOWN_DEFECTS):
        for key, reason in register.items():
            # A one-line reason is a reason nobody can act on; these have to survive being read.
            assert len(reason) > 80, (key, reason)


def test_every_known_defect_is_a_step_the_walk_actually_reaches() -> None:
    """A pinned defect on an operation nothing requests would be a claim with no evidence behind it."""
    walked = {step.operation_id for step in STEPS}
    assert set(KNOWN_DEFECTS) <= walked, sorted(set(KNOWN_DEFECTS) - walked)


def test_a_pinned_defect_declares_a_failing_status() -> None:
    """The pin has to be in the step, not only in the register, or the walk would pass on a fixed route
    and the register would keep claiming a bug that no longer exists."""
    by_id = {step.operation_id: step for step in STEPS}
    for operation in KNOWN_DEFECTS:
        expected = by_id[operation].expect
        assert all(status >= 400 for status in expected), (operation, expected)


@pytest.mark.slow_walk
def test_the_walk_runs_green_against_a_fixture_backend() -> None:
    """The whole point: every declared write operation is requested and answers as declared.

    One backend for the walk, because `fixture_backend` serialises on a cross-process lock — two would
    queue, and the second would be talking to content the first had already destroyed.
    """
    with fixture_backend() as backend:
        answered, failures = walk(backend)
        reached = reached_operations(backend)

    assert failures == [], failures
    assert len(answered) == len(STEPS), sorted({s.operation_id for s in STEPS} - set(answered))

    # The server's own log is the measurement; the walk's intentions are not evidence. A *pinned
    # defect* is deliberately absent from it: `parse_requested_routes` counts only 2xx, because a 4xx
    # or 5xx means the guard ran rather than the handler. So a broken operation stays dark in the
    # register by definition, which is the right answer and worth asserting rather than working around.
    expected = {step.operation_id for step in STEPS} - set(KNOWN_DEFECTS)
    assert expected <= reached, sorted(expected - reached)
    assert set(KNOWN_DEFECTS).isdisjoint(reached), (
        "a pinned-broken operation appears as successfully requested, so either it is fixed (remove "
        "the KNOWN_DEFECTS entry) or the log parser has started counting non-2xx answers"
    )
