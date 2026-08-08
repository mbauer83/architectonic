"""What a write waits for when a verification pass is running.

The whole point of the split, stated as the two cases that must differ. A write arriving during
**acquisition** waits — that is correct, and the wait is bounded by how long reading the tree takes.
A write arriving during **evaluation** must not wait at all, because evaluation holds nothing; that
is the case that used to cost minutes, and the one a regression would quietly restore.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.application.verification.evaluation import EvaluationContext
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

_ENTITY = "APP@1000000831.Waiting.waiting-component"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    entity = root / "model" / "application" / "component" / f"{_ENTITY}.md"
    entity.parent.mkdir(parents=True)
    entity.write_text(
        f"""\
---
artifact-id: {_ENTITY}
artifact-type: entity
entity-type: application-component
name: Waiting Component
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

Fixture component.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    return root


def _write_admission_seconds(gate: WorkspaceMutationGate) -> tuple[threading.Thread, list[float]]:
    """A writer that records how long it waited to be admitted."""
    waited: list[float] = []

    def writer() -> None:
        started = time.monotonic()
        with gate.writing():
            waited.append(time.monotonic() - started)

    return threading.Thread(target=writer, daemon=True), waited


def test_a_write_during_evaluation_is_admitted_without_waiting(repo: Path) -> None:
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    gate = WorkspaceMutationGate()

    with gate.reading():
        snapshot = verifier.acquire(repo, include_diagrams=True)

    evaluating = threading.Event()
    finish_evaluation = threading.Event()
    inner = verifier._verify_inventory_subset

    def slow_subset(*args: object, **kwargs: object) -> object:
        evaluating.set()
        finish_evaluation.wait(timeout=30)
        return inner(*args, **kwargs)  # type: ignore[arg-type]

    verifier._verify_inventory_subset = slow_subset  # type: ignore[method-assign, assignment]

    pass_thread = threading.Thread(
        target=lambda: verifier.verify_all_reporting_pass_mode(
            repo, include_diagrams=True, snapshot=snapshot
        ),
        daemon=True,
    )
    pass_thread.start()
    assert evaluating.wait(timeout=10)

    writer, waited = _write_admission_seconds(gate)
    writer.start()
    writer.join(timeout=10)

    assert waited, "a write issued during evaluation was never admitted"
    assert waited[0] < 1.0, f"it waited {waited[0]:.2f}s — evaluation is holding the gate"

    finish_evaluation.set()
    pass_thread.join(timeout=30)


def test_a_write_during_acquisition_waits_and_then_succeeds(repo: Path) -> None:
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    gate = WorkspaceMutationGate()

    acquiring = threading.Event()
    finish_acquisition = threading.Event()

    def acquire_slowly() -> None:
        with gate.reading():
            acquiring.set()
            finish_acquisition.wait(timeout=30)
            verifier.acquire(repo, include_diagrams=True)

    threading.Thread(target=acquire_slowly, daemon=True).start()
    assert acquiring.wait(timeout=10)

    writer, waited = _write_admission_seconds(gate)
    writer.start()
    writer.join(timeout=1)
    assert not waited, "a write was admitted while the tree was being read"

    finish_acquisition.set()
    writer.join(timeout=30)
    assert waited, "a write issued during acquisition never completed"


def test_the_pass_and_its_evaluation_context_agree_on_what_was_acquired(repo: Path) -> None:
    """The seam these two tests turn on: evaluation holds an image, so it needs no gate."""
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    snapshot = verifier.acquire(repo, include_diagrams=True)

    assert EvaluationContext(snapshot=snapshot).acquired() is snapshot
    with pytest.raises(RuntimeError):
        EvaluationContext().acquired()
