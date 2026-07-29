"""verify_all must verify each document exactly once, in every runtime mode.

Documents live outside the incremental inventory, so the incremental modes append
them separately — but the incremental path's "full" fallback already includes them,
and appending again reported every document issue twice. That duplication is what
made the promotion rollback error appear twice to the user."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

_DOC = "STD@1000000901.DupDoc.duplicate-check-standard"


def _plant_repo(root: Path) -> Path:
    doc_path = root / "docs" / "standard" / "dup" / f"{_DOC}.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(
        f"""\
---
artifact-id: {_DOC}
artifact-type: document
doc-type: standard
title: Duplicate Check Standard
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Scope

Fixture document.
""",
        encoding="utf-8",
    )
    (root / "model").mkdir(parents=True, exist_ok=True)
    return doc_path


@pytest.mark.parametrize("mode", ["full", "incremental"])
def test_each_document_is_verified_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", mode)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    root = tmp_path / "repo"
    doc_path = _plant_repo(root)
    verifier = build_artifact_verifier(
        None, catalogs=build_runtime_catalogs(get_module_registry())
    )

    # First call: incremental mode has no prior state and falls back to a full pass.
    results = verifier.verify_all(root, include_diagrams=True)
    assert [r.path for r in results if r.path == doc_path] == [doc_path]

    # Second call: incremental mode serves from state — documents are outside the
    # incremental inventory and must STILL be verified (once).
    results_again = verifier.verify_all(root, include_diagrams=True)
    assert [r.path for r in results_again if r.path == doc_path] == [doc_path]
