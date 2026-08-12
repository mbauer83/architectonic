"""How often to re-attempt a remote that keeps refusing, and what a poll may do about it.

A fixed poll interval with no memory of failure turns one unreachable remote into an unbounded log
and an unbounded stream of pointless subprocesses. The engagement fetch retried every 60 seconds
with no backoff, no cap and no deduplication, so one six-line git error repeated for as long as the
backend ran — measured at **7.3 MB of the same failure** on an instance whose key needed an agent.

The fix is fewer attempts rather than a quieter log: a remote that has just refused is deferred,
doubling from the poll interval up to a ceiling, and one success clears the record. What remains is
one line per attempt instead of six per minute, and the count is in the line, so "it is still
failing" is a fact the log states rather than one a reader has to infer from repetition.

The three outcomes are distinct because callers act on them differently: a failure is recorded
(the enterprise path persists it as sync health), while a deferral means the record already made
still stands and this poll has nothing to add.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrySchedule:
    """How long a remote is left alone after consecutive failures.

    Doubling from the poll interval, because the first failure is usually transient and the tenth
    never is. The ceiling is what keeps a permanently broken remote — a revoked key, a moved
    origin — from being retried at a rate that only produces log volume, while still recovering
    within half an hour of the cause being fixed, without a restart.
    """

    first_delay_s: float = 60.0
    ceiling_s: float = 1800.0

    def delay_after(self, consecutive_failures: int) -> float:
        if consecutive_failures <= 1:
            return self.first_delay_s
        return min(self.ceiling_s, self.first_delay_s * 2.0 ** (consecutive_failures - 1))


@dataclass(frozen=True)
class Fetched:
    """The remote answered. Any failure record for it has been cleared."""

    after_failures: int = 0


@dataclass(frozen=True)
class FetchDeferred:
    """Not attempted: this remote failed recently and its deferral has not elapsed."""

    retry_in_s: float
    consecutive_failures: int


@dataclass(frozen=True)
class FetchFailed:
    """The remote refused, and when the next attempt becomes due."""

    reason: str
    consecutive_failures: int
    retry_in_s: float


FetchOutcome = Fetched | FetchDeferred | FetchFailed


@dataclass
class FetchAttempts:
    """Per-remote memory of consecutive failures and the deferral each one earns.

    The clock is injected: a schedule spanning half an hour is otherwise only assertable by waiting
    it out, and monotonic time is a dependency like any other.
    """

    schedule: RetrySchedule = field(default_factory=RetrySchedule)
    now: Callable[[], float] = time.monotonic
    _failures: dict[Path, int] = field(default_factory=dict, init=False)
    _not_before: dict[Path, float] = field(default_factory=dict, init=False)

    def deferral(self, repo: Path) -> FetchDeferred | None:
        """Why this remote is not to be attempted yet, or None when it is due."""
        not_before = self._not_before.get(repo)
        if not_before is None or self.now() >= not_before:
            return None
        return FetchDeferred(
            retry_in_s=not_before - self.now(), consecutive_failures=self._failures.get(repo, 0)
        )

    def failed(self, repo: Path, reason: str) -> FetchFailed:
        consecutive = self._failures.get(repo, 0) + 1
        delay = self.schedule.delay_after(consecutive)
        self._failures[repo] = consecutive
        self._not_before[repo] = self.now() + delay
        return FetchFailed(reason=reason, consecutive_failures=consecutive, retry_in_s=delay)

    def succeeded(self, repo: Path) -> Fetched:
        self._not_before.pop(repo, None)
        return Fetched(after_failures=self._failures.pop(repo, 0))


def report_attempt(repo: Path, outcome: FetchOutcome) -> None:
    """Say what this attempt was, in the terms the deferral exists to keep bounded.

    Here rather than at the call site because the wording *is* the point of this module: the volume
    it saves depends on git's stderr being carried once per episode and on every later line stating
    the count instead. One place to read that decision, and one place to change it.
    """
    match outcome:
        case FetchDeferred(retry_in_s=retry_in, consecutive_failures=failures):
            logger.debug(
                "skipping fetch for %s: %d consecutive failure(s), next attempt in %.0fs",
                repo, failures, retry_in,
            )
        case FetchFailed(reason=reason, consecutive_failures=failures, retry_in_s=retry_in):
            logger.warning(
                "fetch failed for %s — attempt %d, next in %.0fs%s",
                repo, failures, retry_in, f": {reason}" if failures == 1 else "",
            )
        case Fetched(after_failures=failures) if failures:
            logger.info("fetch recovered for %s after %d failed attempt(s)", repo, failures)
        case Fetched():
            pass
