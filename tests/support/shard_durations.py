"""Whether the recorded test durations still describe the suite that CI splits into shards.

pytest-split balances the CI shards from `.test_durations`. A test with no recorded duration is given
the mean, so as the suite grows past the file the balance degrades without any message: on 2026-11-27
the file named 8,148 of ~17,600 collected tests, one shard ran 16 minutes against another's 5, and the
v0.12.0 tag's run stopped at the suite's 20-minute cap (B142). The check below makes that a failure
at collection, in the run that splits, so it costs no extra job.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

#: The share of collected tests that may lack a recorded duration before the split is refused. New
#: tests arrive between re-measures, and a tenth of the suite at the mean is still a balance the
#: three shards absorb; 46 % unrecorded is what broke the cap.
MAX_UNRECORDED_SHARE = 0.10

REMEASURE_COMMAND = "uv run pytest -n 6 --store-durations -q"


@dataclass(frozen=True)
class DurationCoverage:
    """How many of the collected tests the durations file has a recorded time for."""

    collected: int
    unrecorded: int

    @property
    def unrecorded_share(self) -> float:
        return self.unrecorded / self.collected if self.collected else 0.0

    @property
    def is_stale(self) -> bool:
        return self.unrecorded_share > MAX_UNRECORDED_SHARE

    def refusal(self, durations_path: str) -> str:
        return (
            f"{durations_path} has no recorded duration for {self.unrecorded} of {self.collected} collected "
            f"tests ({self.unrecorded_share:.0%}, more than the {MAX_UNRECORDED_SHARE:.0%} allowed), so the "
            f"shards would be balanced on guesses. Re-measure it with `{REMEASURE_COMMAND}` and commit it."
        )


def duration_coverage(collected_ids: Iterable[str], recorded_ids: Collection[str]) -> DurationCoverage:
    """Count the collected test ids that *recorded_ids* has no duration for."""
    collected = list(collected_ids)
    return DurationCoverage(
        collected=len(collected),
        unrecorded=sum(1 for node_id in collected if node_id not in recorded_ids),
    )
