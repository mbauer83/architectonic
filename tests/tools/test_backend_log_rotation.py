"""The backend log stays bounded, and only the log this process is actually writing to is rotated.

`.arch/backend.log` reached 62 MB over 491,225 lines and had to be truncated by hand. Rotation is at
the descriptor level rather than through a logging handler, because the file is what the process's
stdout and stderr *are* — so the property to check is that output written after a rotation lands in
the new file, which only a real process can demonstrate. Hence the subprocess: an in-process test
would have to redirect pytest's own stdout to assert anything at all.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.config.settings import backend_log_generations, backend_log_max_bytes
from src.infrastructure.backend.log_rotation import (
    RotationPolicy,
    output_goes_to,
    policy_from_settings,
    rotate_if_oversized,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Writes past the threshold three times over, so the last rotation has to drop a generation.
_DRIVER = """
import sys
from pathlib import Path

from src.infrastructure.backend.log_rotation import RotationPolicy, point_output_at, rotate_if_oversized

log = Path(sys.argv[1])
policy = RotationPolicy(max_bytes=4096, generations=2)
point_output_at(log)
for attempt in range(3):
    print("f" * 5000)
    print(f"attempt={attempt} rotated={rotate_if_oversized(log, policy)}", flush=True)
"""


def _generation(log: Path, index: int) -> Path:
    return log.with_name(f"{log.name}.{index}")


def test_output_after_a_rotation_lands_in_the_new_log(tmp_path: Path) -> None:
    driver = tmp_path / "rotate_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    log = tmp_path / "backend.log"

    done = subprocess.run(
        [sys.executable, str(driver), str(log)],
        cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=120, check=False,
    )

    assert done.returncode == 0, done.stderr
    # Each round rotated, and the record of the *last* one is in the live file — which is the point:
    # the process kept writing to the log rather than to the inode it renamed away.
    assert "attempt=2 rotated=True" in log.read_text(encoding="utf-8")
    assert _generation(log, 1).exists()
    assert _generation(log, 2).exists()
    # Two generations means two: the third rotation drops the oldest rather than accumulating.
    assert not _generation(log, 3).exists()


def test_a_log_this_process_does_not_write_to_is_left_alone(tmp_path: Path) -> None:
    """The guard that keeps a foreground backend's console: pytest's stdout is not this file."""
    log = tmp_path / "someone-elses.log"
    log.write_text("x" * 8192, encoding="utf-8")

    assert output_goes_to(log) is False
    assert rotate_if_oversized(log, RotationPolicy(max_bytes=1024, generations=1)) is False
    assert log.read_text(encoding="utf-8") == "x" * 8192
    assert not _generation(log, 1).exists()


def test_a_log_within_its_policy_is_not_rotated(tmp_path: Path) -> None:
    log = tmp_path / "small.log"
    log.write_text("still small", encoding="utf-8")

    assert rotate_if_oversized(log, RotationPolicy(max_bytes=1024 * 1024, generations=1)) is False
    assert not _generation(log, 1).exists()


def test_the_policy_states_the_disk_it_can_cost() -> None:
    policy = RotationPolicy(max_bytes=1024, generations=3)

    assert policy.bounded_at_bytes == 4096


def test_the_shipped_policy_bounds_the_log() -> None:
    """A default that does not bound anything would leave the register's 62 MB reachable again."""
    policy = policy_from_settings()

    assert policy.max_bytes == backend_log_max_bytes()
    assert policy.generations == backend_log_generations()
    assert 0 < policy.bounded_at_bytes <= 128 * 1024 * 1024


@pytest.mark.parametrize("configured", ["", "not a number", None, 0, -5])
def test_an_unusable_size_falls_back_to_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch, configured: object
) -> None:
    """A settings document is hand-edited, and a log that stops being bounded must not be silent."""
    monkeypatch.setattr(
        "src.config.settings.load_settings",
        lambda: {"backend": {"log_max_bytes": configured, "log_generations": configured}},
    )

    assert backend_log_max_bytes() >= 4096
    assert backend_log_generations() >= 1
