"""`--daemon` waits for the process, not for a number somebody guessed.

The wait was a fixed 15-second deadline. Startup builds the artifact index by scanning every model
file, so its duration is a function of the repository's size — measured at roughly 1.1 ms per file,
which puts 15 seconds at about 13,600 files. Past that the command reported

    timed out waiting for backend on port 8188

for a backend that was starting normally and went on to serve. A false failure, and the kind that
teaches an operator to distrust the tool.

The process answers the question the deadline was guessing at: still alive means still starting, and
exited means failed — which is now reported *at once* instead of after the full timeout.
"""

from __future__ import annotations

import pytest

from src.infrastructure.backend.backend_probe import DAEMON_BACKSTOP_SECONDS, await_backend_startup


class _Clock:
    """A clock that only advances when the code under test sleeps, so no test waits in real time."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _after(n: int):
    """A predicate false for the first *n* calls, then true."""
    calls = {"n": 0}

    def predicate() -> bool:
        calls["n"] += 1
        return calls["n"] > n

    return predicate


class TestAStartingBackend:
    def test_a_backend_that_answers_at_once_is_serving(self) -> None:
        clock = _Clock()

        verdict = await_backend_startup(lambda: True, lambda: True, sleep=clock.sleep, now=clock.now)

        assert verdict == "serving"
        assert clock.t == 0.0

    def test_it_keeps_waiting_far_past_the_old_fifteen_second_deadline(self) -> None:
        """The regression: 15s of polling at 0.25s is 60 polls, and a large repository needs more."""
        clock = _Clock()

        verdict = await_backend_startup(
            _after(400), lambda: True, sleep=clock.sleep, now=clock.now
        )

        assert verdict == "serving"
        assert clock.t > 15.0, "gave up inside the deadline this replaced"

    def test_the_wait_is_bounded_by_the_process_not_by_the_corpus(self) -> None:
        """Whatever the repository's size, a live process is still starting."""
        clock = _Clock()

        verdict = await_backend_startup(
            _after(2000), lambda: True, sleep=clock.sleep, now=clock.now
        )

        assert verdict == "serving"


class TestAFailedStart:
    def test_a_process_that_exits_is_reported_at_once(self) -> None:
        """It used to cost the full timeout to learn what was already true."""
        clock = _Clock()

        verdict = await_backend_startup(lambda: False, lambda: False, sleep=clock.sleep, now=clock.now)

        assert verdict == "exited"
        assert clock.t == 0.0, "waited for a process that was already gone"

    def test_a_backend_that_became_ready_as_it_was_checked_is_not_called_a_failure(self) -> None:
        """Ready-then-gone between the two checks must not be decided by check order alone."""
        clock = _Clock()
        serving = _after(1)  # false on the liveness-adjacent probe, true on the re-probe

        verdict = await_backend_startup(serving, lambda: False, sleep=clock.sleep, now=clock.now)

        assert verdict == "serving"

    def test_a_process_that_neither_serves_nor_exits_hits_the_backstop(self) -> None:
        clock = _Clock()

        verdict = await_backend_startup(lambda: False, lambda: True, sleep=clock.sleep, now=clock.now)

        assert verdict == "backstop"
        assert clock.t >= DAEMON_BACKSTOP_SECONDS

    @pytest.mark.parametrize("backstop", [1.0, 5.0])
    def test_the_backstop_is_the_caller_s_to_set(self, backstop: float) -> None:
        clock = _Clock()

        await_backend_startup(
            lambda: False, lambda: True, backstop_s=backstop, sleep=clock.sleep, now=clock.now
        )

        assert backstop <= clock.t < backstop + 1.0
