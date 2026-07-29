"""How a failure mode attaches to the existing analysis spine, and what it may not do.

The point of the vocabulary is that it introduces no parallel effect or consequence concept: a
failure mode's effect *is* a hazard already on the causal spine, and its cause is the same
loss-scenario concept that already explains unsafe control actions. These tests assert the four
permitted pairs are legal against the real registry, and that the obvious wrong shapes — a failure
mode leading straight to a loss, or being detected by something other than a control — are not.
"""

from __future__ import annotations

import pytest

from src.infrastructure.app_bootstrap import build_module_registry


@pytest.fixture(scope="module")
def permitted() -> object:
    registry = build_module_registry(complete_vocabulary=True)
    return registry.aggregated_permitted_relationships()


def _legal(permitted: object, source: str, target: str) -> frozenset[str]:
    return permitted.permitted_connection_types(source, target)  # type: ignore[attr-defined]


class TestTheEffectAndCauseReuseTheSpine:
    def test_a_failure_mode_leads_to_a_hazard(self, permitted: object) -> None:
        """The effect is a hazard the analysis already holds — not a new effect node type."""
        assert "leads-to" in _legal(permitted, "failure-mode", "hazard")

    def test_a_loss_scenario_explains_a_failure_mode(self, permitted: object) -> None:
        """`explains` is already the causal-story relation; the cause side needs nothing new."""
        assert "explains" in _legal(permitted, "loss-scenario", "failure-mode")

    def test_a_failure_mode_does_not_reach_a_loss_directly(self, permitted: object) -> None:
        """Short-circuiting the hazard would put consequence reasoning on the failure mode and
        start a second consequence vocabulary beside the spine."""
        assert _legal(permitted, "failure-mode", "loss") == frozenset()


class TestPreventionAndDetectionControls:
    def test_a_failure_mode_derives_a_prevention_control(self, permitted: object) -> None:
        assert "derives" in _legal(permitted, "failure-mode", "assurance-constraint")

    def test_a_constraint_detects_a_failure_mode(self, permitted: object) -> None:
        assert "detects" in _legal(permitted, "assurance-constraint", "failure-mode")

    def test_detection_points_from_the_control_to_the_failure(self, permitted: object) -> None:
        """Direction carries the meaning: the control does the detecting."""
        assert "detects" not in _legal(permitted, "failure-mode", "assurance-constraint")

    def test_nothing_else_detects(self, permitted: object) -> None:
        """`detects` earns its place by saying one thing only. Letting other pairs use it would
        make it the vague relation `prevents` was rejected for being."""
        offenders = [
            (source, target)
            for source in ("hazard", "loss", "loss-scenario", "unsafe-control-action", "failure-mode", "risk")
            for target in ("failure-mode", "hazard", "loss", "assurance-constraint")
            if "detects" in _legal(permitted, source, target)
        ]
        assert offenders == []

    def test_a_constraint_still_mitigates_only_a_loss(self, permitted: object) -> None:
        """The neighbouring relation keeps its own subject, so the two cannot be conflated."""
        assert "mitigates" in _legal(permitted, "assurance-constraint", "loss")
        assert "mitigates" not in _legal(permitted, "assurance-constraint", "failure-mode")


class TestTheTypeIsRegistered:
    def test_the_failure_mode_type_exists_with_its_own_prefix(self) -> None:
        registry = build_module_registry(complete_vocabulary=True)

        info = registry.all_entity_types()["failure-mode"]

        assert info.prefix == "FMD"

    def test_failure_mode_analysis_is_a_recognised_method(self) -> None:
        from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS

        assert "FMEA" in ANALYSIS_METHODS
