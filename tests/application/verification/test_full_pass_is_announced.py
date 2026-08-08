"""A pass that will take minutes says so before it starts, and says why.

A full pass after an upgrade is correct — the verifier engine's signature changes, so every cached
result is stale. What was not correct is learning that from a client timeout: the call returned
nothing for minutes while the backend looked hung, and the operator had no way to tell a first-run
cost from a defect. The refusal costs milliseconds and carries the reason, so the decision to spend
the minutes is an informed one.

The reason is reported verbatim from the four conditions rather than summarised, because they mean
different things to whoever reads them: "no prior state" is a first run, while "the verifier engine
changed" is what every release produces.
"""

from __future__ import annotations

import pytest

from src.application.verification.artifact_verifier_incremental import (
    IncrementalState,
    full_pass_reason,
    requires_full_pass,
)

ENGINE = "engine-sig-1"


def _state(**overrides: object) -> IncrementalState:
    base: dict[str, object] = {
        "schema_version": 2,
        "engine_signature": ENGINE,
        "include_diagrams": True,
        "git_head": None,
        "snapshots": {},
        "results": {},
        "include_registry": True,
    }
    base.update(overrides)
    return IncrementalState(**base)  # type: ignore[arg-type]


def _reason(prev: IncrementalState | None, **kw: object) -> str | None:
    args: dict[str, object] = {"include_diagrams": True, "engine_sig": ENGINE, "has_registry": True}
    args.update(kw)
    return full_pass_reason(prev, **args)  # type: ignore[arg-type]


class TestEachTriggerNamesItself:
    def test_no_prior_state(self) -> None:
        assert _reason(None) == "no prior verification state for this repository"

    def test_diagram_scope_changed(self) -> None:
        assert "diagram scope" in (_reason(_state(include_diagrams=False)) or "")

    def test_engine_changed(self) -> None:
        """What every upgrade produces — the case that prompted this."""
        assert "verifier engine" in (_reason(_state(engine_signature="other")) or "")

    def test_registry_availability_changed(self) -> None:
        assert "registry availability" in (_reason(_state(), has_registry=False) or "")

    def test_a_reusable_cache_has_nothing_to_report(self) -> None:
        assert _reason(_state()) is None


class TestTheBooleanAndTheReasonCannotDisagree:
    """`requires_full_pass` is derived from the reason, so there is one decision, not two."""

    @pytest.mark.parametrize(
        "prev, kw",
        [
            (None, {}),
            (_state(include_diagrams=False), {}),
            (_state(engine_signature="other"), {}),
            (_state(), {"has_registry": False}),
            (_state(), {}),
        ],
    )
    def test_they_agree(self, prev: IncrementalState | None, kw: dict[str, object]) -> None:
        args: dict[str, object] = {"include_diagrams": True, "engine_sig": ENGINE, "has_registry": True}
        args.update(kw)
        assert requires_full_pass(prev, **args) is (full_pass_reason(prev, **args) is not None)  # type: ignore[arg-type]
