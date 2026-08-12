"""A remote that keeps refusing is attempted less often, and said once rather than every minute.

The engagement fetch retried every 60 seconds with no backoff, no cap and no deduplication, so one
unreachable origin wrote git's several lines of stderr into `.arch/backend.log` for as long as the
process ran — measured at 7.3 MB of the same failure. Both properties are asserted here: the number
of *attempts* over a span of time is bounded, and the count of failures is what the later lines carry.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from src.infrastructure.git.fetch_attempts import (
    FetchAttempts,
    FetchDeferred,
    Fetched,
    FetchFailed,
    RetrySchedule,
)
from src.infrastructure.git.git_sync import GitSyncManager, RepoSpec

_REPO = Path("/tmp/a-repo-this-test-never-reads")
_OTHER = Path("/tmp/another-repo-this-test-never-reads")


class _Clock:
    """A monotonic clock the test advances, so half an hour of schedule costs no waiting."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def read(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class TestRetrySchedule:
    def test_the_first_failure_waits_one_poll_interval(self) -> None:
        assert RetrySchedule(first_delay_s=60.0).delay_after(1) == 60.0

    def test_each_further_failure_doubles(self) -> None:
        schedule = RetrySchedule(first_delay_s=60.0, ceiling_s=10_000.0)

        assert [schedule.delay_after(n) for n in (1, 2, 3, 4)] == [60.0, 120.0, 240.0, 480.0]

    def test_the_wait_stops_growing_at_the_ceiling(self) -> None:
        """A permanently broken remote must not end up retried once a week."""
        schedule = RetrySchedule(first_delay_s=60.0, ceiling_s=1800.0)

        assert schedule.delay_after(20) == 1800.0
        assert schedule.delay_after(500) == 1800.0


class TestFetchAttempts:
    def test_a_remote_with_no_history_is_due(self) -> None:
        assert FetchAttempts(now=_Clock().read).deferral(_REPO) is None

    def test_a_failure_defers_the_next_attempt(self) -> None:
        clock = _Clock()
        attempts = FetchAttempts(RetrySchedule(first_delay_s=60.0), now=clock.read)

        failure = attempts.failed(_REPO, "connection refused")

        assert failure == FetchFailed(
            reason="connection refused", consecutive_failures=1, retry_in_s=60.0
        )
        clock.advance(30.0)
        assert attempts.deferral(_REPO) == FetchDeferred(retry_in_s=30.0, consecutive_failures=1)

    def test_the_deferral_elapses(self) -> None:
        clock = _Clock()
        attempts = FetchAttempts(RetrySchedule(first_delay_s=60.0), now=clock.read)
        attempts.failed(_REPO, "refused")

        clock.advance(60.0)

        assert attempts.deferral(_REPO) is None

    def test_consecutive_failures_accumulate(self) -> None:
        clock = _Clock()
        attempts = FetchAttempts(RetrySchedule(first_delay_s=60.0, ceiling_s=10_000.0), now=clock.read)

        attempts.failed(_REPO, "refused")
        clock.advance(60.0)
        second = attempts.failed(_REPO, "refused")

        assert second.consecutive_failures == 2
        assert second.retry_in_s == 120.0

    def test_success_clears_the_record_and_reports_what_it_ends(self) -> None:
        clock = _Clock()
        attempts = FetchAttempts(RetrySchedule(first_delay_s=60.0), now=clock.read)
        attempts.failed(_REPO, "refused")
        clock.advance(60.0)
        attempts.failed(_REPO, "refused")

        assert attempts.succeeded(_REPO) == Fetched(after_failures=2)
        # Cleared, so a later failure starts a new episode rather than continuing the old one.
        assert attempts.deferral(_REPO) is None
        assert attempts.failed(_REPO, "refused").consecutive_failures == 1

    def test_remotes_are_deferred_independently(self) -> None:
        attempts = FetchAttempts(RetrySchedule(first_delay_s=60.0), now=_Clock().read)

        attempts.failed(_REPO, "refused")

        assert attempts.deferral(_REPO) is not None
        assert attempts.deferral(_OTHER) is None


def _manager(clock: _Clock) -> GitSyncManager:
    return GitSyncManager(
        [RepoSpec(path=_REPO, role="engagement")],
        fetch_attempts=FetchAttempts(
            RetrySchedule(first_delay_s=60.0, ceiling_s=1800.0), now=clock.read
        ),
    )


#: What `GitSyncManager._git` is, from a caller's side. Named the same way `git_sync_m4` names it.
GitRunner = Callable[..., Awaitable[tuple[int, str, str]]]


def _stub_git(invocations: list[tuple[str, ...]], *, failing: bool) -> GitRunner:
    """Stand in for the git subprocess, so a poll costs neither a process nor a network."""

    async def run(repo: Path, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        invocations.append(args)
        if failing:
            return 128, "", "fatal: could not read Username for 'https://example.invalid'\nline two\n"
        return 0, "", ""

    return run


def test_a_failing_remote_is_attempted_a_bounded_number_of_times(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Twenty polls of an unreachable origin, at the interval the poll loop actually uses."""
    clock = _Clock()
    manager = _manager(clock)
    invocations: list[tuple[str, ...]] = []
    monkeypatch.setattr(manager, "_git", _stub_git(invocations, failing=True))

    async def twenty_polls() -> None:
        for _tick in range(20):
            await manager._fetch_origin(_REPO)
            clock.advance(60.0)

    with caplog.at_level(logging.WARNING):
        asyncio.run(twenty_polls())

    fetches = [args for args in invocations if args[:1] == ("fetch",)]
    # Without the deferral this was twenty attempts and twenty multi-line failures. With it, the same
    # twenty minutes cost five: 60s, 120s, 240s, 480s, 960s.
    assert len(fetches) == 5, fetches
    # git's stderr appears once — the first attempt of the episode — and later lines carry the count.
    assert caplog.text.count("could not read Username") == 1
    assert "attempt 5" in caplog.text


def test_a_deferred_poll_reports_no_failure_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """The distinction the enterprise path acts on: a deferral adds nothing to the health record."""
    clock = _Clock()
    manager = _manager(clock)
    monkeypatch.setattr(manager, "_git", _stub_git([], failing=True))

    async def two_polls() -> tuple[object, object]:
        first = await manager._fetch_origin(_REPO)
        clock.advance(1.0)
        return first, await manager._fetch_origin(_REPO)

    first, second = asyncio.run(two_polls())

    assert isinstance(first, FetchFailed)
    assert second == FetchDeferred(retry_in_s=59.0, consecutive_failures=1)


def test_recovery_is_reported_with_what_it_ended(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _Clock()
    manager = _manager(clock)
    monkeypatch.setattr(manager, "_git", _stub_git([], failing=True))

    async def fail_then_recover() -> object:
        await manager._fetch_origin(_REPO)
        clock.advance(60.0)
        monkeypatch.setattr(manager, "_git", _stub_git([], failing=False))
        return await manager._fetch_origin(_REPO)

    with caplog.at_level(logging.INFO):
        outcome = asyncio.run(fail_then_recover())

    assert outcome == Fetched(after_failures=1)
    assert "fetch recovered" in caplog.text
