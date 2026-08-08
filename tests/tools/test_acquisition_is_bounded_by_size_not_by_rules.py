"""Acquisition costs what the repository *is*, never what verifying it costs.

This is the property the whole split rests on, and the only one that can fail silently. Exclusivity
is held for acquisition alone; if acquisition ever started doing evaluation's work — resolving a
reference, consulting a catalog, running a rule — the exclusive window would grow back into minutes
and nothing would report it. So the assertion is not "acquisition is fast on this machine", which a
fast machine passes regardless: it is that inflating per-file rule cost tenfold leaves acquisition
unchanged.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

_FILES = 1000
_ACQUISITION_CEILING_SECONDS = 2.0


def _plant_corpus(root: Path, count: int) -> None:
    domain = root / "model" / "application" / "component"
    domain.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        artifact_id = f"APP@10000010{index:04d}.Bulk{index:04d}.bulk-component-{index}"
        (domain / f"{artifact_id}.md").write_text(
            f"""\
---
artifact-id: {artifact_id}
artifact-type: entity
entity-type: application-component
name: Bulk Component {index}
status: draft
version: 0.1.0
last-updated: '2026-01-01'
---

## Description

One of {count} fixture components.
""",
            encoding="utf-8",
        )


@pytest.fixture()
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    _plant_corpus(root, _FILES)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")
    return root


def _acquire_seconds(root: Path) -> float:
    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    started = time.monotonic()
    snapshot = verifier.acquire(root, include_diagrams=True)
    elapsed = time.monotonic() - started
    assert len(snapshot.contents) >= _FILES
    return elapsed


def test_acquiring_a_thousand_files_stays_within_the_stated_ceiling(corpus: Path) -> None:
    elapsed = _acquire_seconds(corpus)

    assert elapsed <= _ACQUISITION_CEILING_SECONDS, (
        f"acquisition of {_FILES} files took {elapsed:.2f}s, over the {_ACQUISITION_CEILING_SECONDS}s ceiling"
    )


def test_inflating_per_file_rule_cost_leaves_acquisition_unchanged(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half that actually tests the split. A fast machine passes the ceiling either way.

    Timing alone would be a weak assertion here, so the load-bearing one is the call count: rule
    cost can be inflated by any factor and acquisition still applies no rule at all.
    """
    from src.application.verification import artifact_verifier

    baseline = _acquire_seconds(corpus)

    real = artifact_verifier.verify_entity
    calls = 0

    def ten_times_the_work(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        for _ in range(9):
            real(*args, **kwargs)  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(artifact_verifier, "verify_entity", ten_times_the_work)

    verifier = build_artifact_verifier(None, catalogs=build_runtime_catalogs(get_module_registry()))
    started = time.monotonic()
    snapshot = verifier.acquire(corpus, include_diagrams=True)
    inflated = time.monotonic() - started

    assert calls == 0, "acquisition applied a verification rule — it is doing evaluation's work"
    # And the inflation is real: the same rule, reached through the pass, runs ten times per file.
    verifier.verify_entity_file(next(iter(snapshot.contents)))
    assert calls == 1

    assert inflated <= max(baseline * 3, 0.5), (
        f"acquisition went {baseline:.3f}s → {inflated:.3f}s when rule cost rose 10×"
    )
