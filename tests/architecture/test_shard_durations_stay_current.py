"""A sharded run refuses durations that no longer name the suite (B142).

The v0.12.0 tag's CI run stopped at the 20-minute cap because `.test_durations` named 8,148 of
~17,600 tests, and nothing said so. The rule lives in `tests.support.shard_durations` and is applied by
the root conftest at collection whenever pytest runs with `--splits`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.support.shard_durations import MAX_UNRECORDED_SHARE, REMEASURE_COMMAND, duration_coverage

_REPO = Path(__file__).resolve().parents[2]


def test_a_fully_recorded_suite_is_current() -> None:
    coverage = duration_coverage(["a", "b"], {"a": 1.0, "b": 2.0})
    assert (coverage.collected, coverage.unrecorded, coverage.is_stale) == (2, 0, False)


def test_the_threshold_itself_is_still_current() -> None:
    collected = [f"t{i}" for i in range(100)]
    recorded = {node_id: 1.0 for node_id in collected[: 100 - round(MAX_UNRECORDED_SHARE * 100)]}
    assert not duration_coverage(collected, recorded).is_stale


def test_one_more_unrecorded_test_is_stale_and_says_how_to_remeasure() -> None:
    collected = [f"t{i}" for i in range(100)]
    recorded = {node_id: 1.0 for node_id in collected[: 99 - round(MAX_UNRECORDED_SHARE * 100)]}
    coverage = duration_coverage(collected, recorded)
    assert coverage.is_stale
    refusal = coverage.refusal(".test_durations")
    assert REMEASURE_COMMAND in refusal
    assert f"{coverage.unrecorded} of 100" in refusal


def test_recorded_durations_of_tests_that_no_longer_exist_do_not_count() -> None:
    assert not duration_coverage(["a"], {"a": 1.0, "gone": 9.0}).is_stale


def test_an_empty_collection_is_not_stale() -> None:
    assert not duration_coverage([], {}).is_stale


def test_a_sharded_run_over_a_stale_file_is_refused_at_collection(tmp_path: Path) -> None:
    """The conftest applies the rule: a split against an empty durations file stops before any test runs."""
    durations = tmp_path / "durations.json"
    durations.write_text(json.dumps({}), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-n", "0", "--co", "-q",
            "--splits", "2", "--group", "1", "--durations-path", str(durations),
            "tests/architecture/test_shard_durations_stay_current.py",
        ],
        cwd=_REPO, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode != 0
    assert REMEASURE_COMMAND in completed.stdout + completed.stderr
