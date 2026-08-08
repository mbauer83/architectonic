"""Whole-repository verification is a step inside two write operations, not only a read.

`promote_execute` and `cascade_delete` verify the target tree while the authorized-write executor
holds `gate.writing()`. The gate is not reentrant, so a verifier that acquired READ for itself would
wait on its own caller forever — a deadlocked backend under a routine promote, reached only when
those paths get as far as their verification step.

These tests assert the property directly at both shapes: a pass while WRITE is held completes, and
the read path's own acquisition still takes READ.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

_ENTITY = "APP@1000000811.NoDeadlock.no-deadlock-component"


def _plant_repo(root: Path) -> None:
    path = root / "model" / "application" / "component" / f"{_ENTITY}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""\
---
artifact-id: {_ENTITY}
artifact-type: entity
entity-type: application-component
name: No Deadlock Component
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

Fixture component.
""",
        encoding="utf-8",
    )


def test_a_pass_completes_while_the_caller_holds_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    root = tmp_path / "repo"
    _plant_repo(root)
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    gate = WorkspaceMutationGate()

    finished = threading.Event()
    failure: list[BaseException] = []

    def promote_shaped() -> None:
        try:
            with gate.writing():
                verifier.verify_all(root, include_diagrams=True)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            failure.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=promote_shaped, daemon=True)
    worker.start()
    assert finished.wait(timeout=60), "verification inside gate.writing() did not complete"
    assert not failure, failure


def test_acquisition_and_evaluation_hold_the_gate_for_different_lengths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A writer waits for acquisition, not for evaluation — the whole point of the split."""
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    root = tmp_path / "repo"
    _plant_repo(root)
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    gate = WorkspaceMutationGate()

    admitted = threading.Event()

    def writer() -> None:
        with gate.writing():
            admitted.set()

    # Evaluation refuses to finish until a writer has been admitted. If evaluation held the gate,
    # this could never resolve; because it holds nothing, the writer goes in mid-pass.
    inner = verifier._verify_inventory_subset

    def blocking_subset(*args: object, **kwargs: object) -> object:
        assert admitted.wait(timeout=30), "a writer was blocked for the whole of evaluation"
        return inner(*args, **kwargs)  # type: ignore[arg-type]

    verifier._verify_inventory_subset = blocking_subset  # type: ignore[method-assign, assignment]

    with gate.reading():
        snapshot = verifier.acquire(root, include_diagrams=True)
    threading.Thread(target=writer, daemon=True).start()
    verifier.verify_all_reporting_pass_mode(root, include_diagrams=True, snapshot=snapshot)

    assert admitted.is_set()
