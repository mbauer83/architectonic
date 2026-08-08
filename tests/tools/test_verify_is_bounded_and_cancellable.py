"""One pass at a time per repository, and a cancelled one leaves no memory of itself.

Two properties, both about what a pass costs when it goes wrong. A second concurrent pass is
refused rather than queued, because queuing makes a caller wait minutes to hear what the first pass
is about to say and lets a retrying client turn one slow answer into an hour of work. And a pass
that stops early must save nothing: incremental state is a claim that named files were verified at
named contents, so a partial one teaches the next pass to trust a region nobody looked at — with no
symptom beyond the repository quietly no longer being checked.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from src.application.verification.evaluation import PassCancellation, VerificationPassCancelled
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.mcp.artifact_mcp import verify_tools
from src.infrastructure.verification.pass_runner import (
    VerificationAlreadyRunning,
    run_verification_pass,
)
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

_ENTITY = "APP@1000000821.Cancel.cancellable-component"


def _plant_second_entity(root: Path) -> None:
    second = root / "model" / "application" / "component" / "APP@1000000822.Cancel2.second-component.md"
    second.write_text(
        """\
---
artifact-id: APP@1000000822.Cancel2.second-component
artifact-type: entity
entity-type: application-component
name: Second Component
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

Fixture component.
""",
        encoding="utf-8",
    )


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    entity = root / "model" / "application" / "component" / f"{_ENTITY}.md"
    entity.parent.mkdir(parents=True)
    entity.write_text(
        f"""\
---
artifact-id: {_ENTITY}
artifact-type: entity
entity-type: application-component
name: Cancellable Component
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

Fixture component.
""",
        encoding="utf-8",
    )
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    return root


class TestASecondPassIsRefused:
    def test_the_runner_refuses_a_concurrent_pass_over_the_same_roots(self) -> None:
        first_running = threading.Event()
        release = threading.Event()

        def blocking(_cancellation: PassCancellation) -> str:
            first_running.set()
            release.wait(timeout=30)
            return "first"

        async def scenario() -> None:
            first = asyncio.create_task(run_verification_pass("roots-a", blocking))
            await asyncio.to_thread(first_running.wait, 10)
            with pytest.raises(VerificationAlreadyRunning):
                await run_verification_pass("roots-a", lambda _c: "second")
            release.set()
            assert await first == "first"

        asyncio.run(scenario())

    def test_different_roots_are_not_refused_against_each_other(self) -> None:
        async def scenario() -> None:
            assert await run_verification_pass("roots-a", lambda _c: "a") == "a"
            assert await run_verification_pass("roots-b", lambda _c: "b") == "b"

        asyncio.run(scenario())

    def test_the_tool_answers_the_refusal_rather_than_raising(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        running = threading.Event()
        release = threading.Event()

        def slow(*args: object, **kwargs: object) -> tuple[dict[str, str], list[object]]:
            running.set()
            release.wait(timeout=30)
            return {}, []

        monkeypatch.setattr(verify_tools, "_verify_every_root", slow)

        async def scenario() -> dict:
            first = asyncio.create_task(
                verify_tools.artifact_verify(
                    repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True
                )
            )
            await asyncio.to_thread(running.wait, 10)
            second = await verify_tools.artifact_verify(
                repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True
            )
            release.set()
            await first
            return second

        out = asyncio.run(scenario())
        assert set(out["pass_mode"].values()) == {"already-running"}
        assert out["results"] == []
        assert "already running" in out["message"]


class TestACancelledPassLeavesNoState:
    def _state_files(self, tmp_path: Path) -> list[Path]:
        state_dir = tmp_path / "verify-state"
        return sorted(state_dir.rglob("*")) if state_dir.exists() else []

    def test_a_pass_cancelled_mid_sweep_writes_no_state(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mid-sweep, not before it: a pass that has verified *some* files is the dangerous one."""
        monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "incremental")
        _plant_second_entity(repo)
        verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))

        class _CancelAfterFirstFile(PassCancellation):
            def __init__(self) -> None:
                super().__init__()
                self.checks = 0

            def raise_if_cancelled(self) -> None:
                self.checks += 1
                if self.checks > 1:
                    self.cancel()
                super().raise_if_cancelled()

        cancellation = _CancelAfterFirstFile()
        with pytest.raises(VerificationPassCancelled):
            verifier.verify_all_reporting_pass_mode(
                repo, include_diagrams=True, cancellation=cancellation
            )

        assert cancellation.checks > 1, "the pass should have reached at least one file"
        assert [p for p in self._state_files(tmp_path) if p.is_file()] == []

    def test_a_cached_pass_is_governed_too(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`incremental-cached` applies no rule, so no per-file check fires — and it still saves."""
        monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "incremental")
        verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
        mode, _ = verifier.verify_all_reporting_pass_mode(repo, include_diagrams=True)
        assert mode == "full"

        before = {p: p.stat().st_mtime_ns for p in self._state_files(tmp_path) if p.is_file()}
        assert before, "the first pass should have written state to overwrite"

        cancellation = PassCancellation()
        cancellation.cancel()
        with pytest.raises(VerificationPassCancelled):
            verifier.verify_all_reporting_pass_mode(
                repo, include_diagrams=True, cancellation=cancellation
            )

        after = {p: p.stat().st_mtime_ns for p in self._state_files(tmp_path) if p.is_file()}
        assert after == before

    def test_cancelling_the_awaiting_task_cancels_the_pass(self) -> None:
        observed: list[bool] = []
        started = threading.Event()

        def watchful(cancellation: PassCancellation) -> str:
            started.set()
            for _ in range(200):
                if cancellation.cancelled:
                    observed.append(True)
                    return "stopped"
                threading.Event().wait(0.05)
            return "ran to completion"

        async def scenario() -> None:
            task = asyncio.create_task(run_verification_pass("roots-c", watchful))
            await asyncio.to_thread(started.wait, 10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        for _ in range(100):
            if observed:
                break
            threading.Event().wait(0.05)
        assert observed == [True]
