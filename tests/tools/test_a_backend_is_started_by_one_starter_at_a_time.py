"""The start lock: one starter of a workspace's backend at a time, and none left behind by a crash."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from src.infrastructure.backend.backend_start_lock import backend_start_lock


@pytest.fixture(autouse=True)
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / ".arch"))
    return tmp_path / ".arch"


def test_a_second_starter_waits_for_the_first_to_finish(tmp_path: Path) -> None:
    order: list[str] = []
    first_holds = threading.Event()

    def first() -> None:
        with backend_start_lock(tmp_path, timeout_s=5):
            first_holds.set()
            time.sleep(0.3)
            order.append("first done")

    holder = threading.Thread(target=first)
    holder.start()
    first_holds.wait(5)
    with backend_start_lock(tmp_path, timeout_s=5):
        order.append("second in")
    holder.join()

    assert order == ["first done", "second in"]


def test_a_starter_that_waits_too_long_is_told_who_holds_the_lock(tmp_path: Path) -> None:
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with backend_start_lock(tmp_path, timeout_s=5):
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    try:
        with pytest.raises(RuntimeError, match=f"pid {os.getpid()}"), backend_start_lock(tmp_path, timeout_s=0.3):
            pass
    finally:
        release.set()
        holder.join()


def test_a_starter_that_died_holding_the_lock_does_not_keep_it(tmp_path: Path, state_dir: Path) -> None:
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from src.infrastructure.backend.backend_start_lock import backend_start_lock\n"
        "with backend_start_lock(Path(sys.argv[1]), timeout_s=5):\n"
        "    print('held', flush=True)\n"
        "    time.sleep(60)\n"
    )
    env = {**os.environ, "ARCH_BACKEND_STATE_DIR": str(state_dir)}
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)], stdout=subprocess.PIPE, text=True, env=env,
        cwd=Path(__file__).resolve().parents[2],
    )
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "held"
        child.kill()
        child.wait(5)

        with backend_start_lock(tmp_path, timeout_s=1):
            pass
    finally:
        if child.poll() is None:
            child.kill()
        if child.stdout is not None:
            child.stdout.close()
