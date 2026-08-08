"""A pass reads the repository once, and judges only what it read.

The split this guards: acquisition touches the filesystem under whatever exclusivity the caller
holds; evaluation — minutes of rule application — touches nothing. A rule that still reaches disk
would silently defeat that, with no symptom other than a diagnostic about a state nobody verified.
So the check is behavioural rather than a grep for ``read_text``: corrupt every file on disk after
acquiring, and demand the same answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.verifier_ports import FileInventoryPort
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

_ENTITY = "APP@1000000801.SnapComp.snapshot-component"


def _plant_repo(root: Path) -> list[Path]:
    entity_path = root / "model" / "application" / "component" / f"{_ENTITY}.md"
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    entity_path.write_text(
        f"""\
---
artifact-id: {_ENTITY}
artifact-type: entity
entity-type: application-component
name: Snapshot Component
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

Fixture component.
""",
        encoding="utf-8",
    )
    doc_path = root / "docs" / "standard" / "snap" / "STD@1000000802.SnapDoc.snapshot-standard.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(
        """\
---
artifact-id: STD@1000000802.SnapDoc.snapshot-standard
artifact-type: document
doc-type: standard
title: Snapshot Standard
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Scope

Fixture document.
""",
        encoding="utf-8",
    )
    return [entity_path, doc_path]


def _build(tmp_path: Path):
    return build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))


def _issue_codes(results: list) -> list[tuple[str, tuple[str, ...]]]:
    return sorted((str(r.path), tuple(sorted(i.code for i in r.issues))) for r in results)


@pytest.mark.parametrize("mode", ["full", "incremental"])
def test_evaluation_ignores_the_filesystem_changing_under_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", mode)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    root = tmp_path / "repo"
    planted = _plant_repo(root)

    intact = _issue_codes(_build(tmp_path).verify_all(root, include_diagrams=True))

    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state-2"))
    verifier = _build(tmp_path)
    snapshot = verifier.acquire(root, include_diagrams=True)
    for path in planted:
        path.write_text("---\nartifact-id: NOPE\n---\n\nnot a model file at all\n", encoding="utf-8")

    after = _issue_codes(
        verifier.verify_all_reporting_pass_mode(root, include_diagrams=True, snapshot=snapshot)[1]
    )
    assert after == intact


class _CountingInventory(FileInventoryPort):
    """Counts sweeps of the filesystem, delegating the sweep itself."""

    def __init__(self, inner: FileInventoryPort) -> None:
        self._inner = inner
        self.builds = 0

    def build(self, repo_path: Path, *, include_diagrams: bool):  # type: ignore[no-untyped-def]
        self.builds += 1
        return self._inner.build(repo_path, include_diagrams=include_diagrams)

    def list_doc_files(self, repo_path: Path) -> list[Path]:
        return self._inner.list_doc_files(repo_path)

    def filter_doc_files(self, repo_path: Path, paths: list[Path]) -> list[Path]:
        return self._inner.filter_doc_files(repo_path, paths)


def test_a_full_pass_reached_from_the_incremental_path_sweeps_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two sweeps persisted the first sweep's snapshots against the second sweep's results."""
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "incremental")
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    root = tmp_path / "repo"
    _plant_repo(root)

    verifier = _build(tmp_path)
    counting = _CountingInventory(verifier._inventory)
    verifier._inventory = counting

    # No stored state, so the incremental path falls straight through to a full pass.
    mode, _ = verifier.verify_all_reporting_pass_mode(root, include_diagrams=True)
    assert mode == "full"
    assert counting.builds == 1
