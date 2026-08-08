"""A verification pass must not be what the backend is doing.

FastMCP calls a synchronous tool directly on the event loop, so a pass measured in minutes made
every other request wait for it — identity, health, the event stream, all of it. The tool is a
coroutine now and its pass runs on a worker of its own.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from src.infrastructure.mcp.artifact_mcp import verify_tools
from src.infrastructure.verification.pass_runner import (
    abandon_verification_passes,
    verification_pass_queue,
)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    return root


def test_the_loop_keeps_serving_while_a_pass_runs(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    served = 0

    def slow_pass(*args: object, **kwargs: object) -> tuple[dict[str, str], list[object]]:
        release.wait(timeout=30)
        return {}, []

    monkeypatch.setattr(verify_tools, "_verify_every_root", slow_pass)

    async def scenario() -> int:
        nonlocal served
        pass_task = asyncio.create_task(
            verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True)
        )
        # Anything else the loop is asked to do while the pass is in flight.
        for _ in range(5):
            await asyncio.sleep(0)
            served += 1
        release.set()
        await pass_task
        return served

    assert asyncio.run(scenario()) == 5


def test_the_pass_runs_on_its_own_worker(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not the default executor, which git-status and group refreshes share."""
    seen: list[str] = []

    def record(*args: object, **kwargs: object) -> tuple[dict[str, str], list[object]]:
        seen.append(threading.current_thread().name)
        return {}, []

    monkeypatch.setattr(verify_tools, "_verify_every_root", record)
    asyncio.run(verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True))

    assert seen and seen[0].startswith("verification-pass-queue")


def test_shutdown_abandons_a_pass_rather_than_waiting_for_it(repo: Path) -> None:
    """A pass owes nothing durable, so the stop budget must not be spent on one."""
    running = threading.Event()
    release = threading.Event()

    def long_pass() -> str:
        running.set()
        release.wait(timeout=30)
        return "finished"

    future = verification_pass_queue.submit(long_pass)
    assert running.wait(timeout=10)

    started = time.monotonic()
    abandon_verification_passes()
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"shutdown waited {elapsed:.2f}s for a pass it owes nothing to"
    release.set()
    future.result(timeout=10)
