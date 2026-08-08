"""What the evaluation half of a pass runs against: an image to judge, and leave to keep judging.

A pass has two halves. Acquisition reads the repository under whatever exclusivity its caller holds
and produces a :class:`RepositorySnapshot`; evaluation applies every rule to that image and holds
nothing. This is what the second half needs, named once instead of threaded as two parameters
through every function between the entry point and a single file.

Cancellation is checked *between files* rather than inside a rule, because that is the grain at
which stopping is both cheap and safe: a rule either ran or did not, and a pass that stops between
two of them has a coherent partial result — which it then discards, because the danger is not the
wasted work but the memory of it. Incremental state records "these files were verified at these
contents"; a partial one teaches the next pass to trust a region nobody looked at.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.verification._verifier_snapshot import RepositorySnapshot
from src.application.verification.artifact_verifier_types import VerificationResult


class VerificationPassCancelled(Exception):
    """Raised inside a pass whose caller has gone away. Never caught by the pass itself.

    Raising, rather than returning a partial answer, is what keeps the promise: every ``save`` sits
    after the work in its own function, so an exception passing through cannot write one.
    """


class PassCancellation:
    """One pass's answer to "should I still be doing this?"."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise VerificationPassCancelled("verification pass cancelled")


@dataclass(frozen=True)
class EvaluationContext:
    """The image a pass judges, and whether it should still be judging it."""

    snapshot: RepositorySnapshot | None = None
    cancellation: PassCancellation | None = None

    def per_file(self, verify: Callable[..., VerificationResult]) -> Callable[[Path], VerificationResult]:
        """Bind a per-file rule to this evaluation: read from the image, stop when unwanted."""
        bound = functools.partial(verify, snapshot=self.snapshot)
        cancellation = self.cancellation
        if cancellation is None:
            return bound

        def checked(path: Path) -> VerificationResult:
            cancellation.raise_if_cancelled()
            return bound(path)

        return checked

    def raise_if_cancelled(self) -> None:
        if self.cancellation is not None:
            self.cancellation.raise_if_cancelled()

    def acquired(self) -> RepositorySnapshot:
        """The image, for the paths that only run once one has been acquired."""
        if self.snapshot is None:
            raise RuntimeError("this evaluation has no acquired snapshot")
        return self.snapshot


#: What a pass runs under when nobody supplied conditions — read from disk, run to completion.
UNCONDITIONAL = EvaluationContext()
