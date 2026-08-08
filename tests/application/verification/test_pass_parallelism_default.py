"""A pass verifies one file at a time by default, and says why in one place.

The pool was not removed for tidiness — it was measured costing on both axes at once, so this holds
the decision against the reflex that produced it. `cpu + 4` is the `ThreadPoolExecutor` default and
looks like the obvious answer for a fan-out; it is the answer for work that *waits*, and rule
evaluation never waits. Anyone raising this again should re-measure first, which is what the
override is for.
"""

from __future__ import annotations

import pytest

from src.application.verification.artifact_verifier_syntax import resolve_worker_count


def test_a_pass_is_sequential_unless_asked_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCH_VERIFY_WORKERS", raising=False)

    assert resolve_worker_count() == 1


def test_the_override_opts_into_parallelism(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCH_VERIFY_WORKERS", "8")

    assert resolve_worker_count() == 8


@pytest.mark.parametrize("value", ["", "0", "-3", "many", "4.5"])
def test_an_unusable_override_leaves_the_default_standing(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """A typo must not silently reintroduce the pool, nor produce a pool of zero threads."""
    monkeypatch.setenv("ARCH_VERIFY_WORKERS", value)

    assert resolve_worker_count() == 1


def test_the_override_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCH_VERIFY_WORKERS", "9999")

    assert resolve_worker_count() == 32
