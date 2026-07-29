"""Verifier rules over failure modes, each with the case that must fire and the case that must not.

The two worth reading closely are `E509` and `W509`.

`E509` lets an assertion *lower* a derived severity — the hazard chain may overstate what one
particular failure does — and refuses to let it raise one above every loss the chain reaches, which
would invent consequence and then let that number drive a priority.

`W509` is the anti-subordination tripwire: a constraint carried as merely accepted while a failure
mode it answers is high priority. A priority band may never close, weaken or defer a safety
obligation, and this is the shape that violation takes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.verification.assurance_verifier import verify_store

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()


def _codes(store: Any) -> list[str]:
    return [issue.code for issue in verify_store(store).issues]


def _failure_mode(store: Any, name: str = "Store returns a stale row", **attributes: object) -> str:
    node_id = str(store.create_node("failure-mode", name))
    if attributes:
        store.update_node(node_id, attributes=attributes)
    return node_id


class TestAFailureModeMustBeAFailureOfSomething:
    def test_an_unbound_failure_mode_is_a_hard_finding(self, store: Any) -> None:
        _failure_mode(store)

        assert "E507" in _codes(store)

    def test_binding_it_to_an_element_satisfies_the_rule(self, store: Any) -> None:
        node_id = _failure_mode(store)
        store.register_arch_ref(node_id, "APP@1", "binds-to")

        assert "E507" not in _codes(store)

    def test_declaring_it_out_of_scope_also_satisfies_the_rule(self, store: Any) -> None:
        """Outside the analysis boundary is a decision, not an omission."""
        node_id = _failure_mode(store)
        store.update_node(node_id, binding_status="out-of-scope")

        assert "E507" not in _codes(store)


class TestTheChainAndTheControls:
    def test_a_failure_mode_reaching_no_hazard_is_reported(self, store: Any) -> None:
        _failure_mode(store)

        assert "W506" in _codes(store)

    def test_linking_an_effect_satisfies_it(self, store: Any) -> None:
        node_id = _failure_mode(store)
        hazard = str(store.create_node("hazard", "Stale data is served"))
        store.add_edge(node_id, hazard, "leads-to")

        assert "W506" not in _codes(store)

    def test_a_failure_mode_nothing_detects_is_reported(self, store: Any) -> None:
        _failure_mode(store)

        assert "W507" in _codes(store)

    def test_a_detection_control_satisfies_it(self, store: Any) -> None:
        node_id = _failure_mode(store)
        control = str(store.create_node("assurance-constraint", "Freshness is asserted on read"))
        store.add_edge(control, node_id, "detects")

        assert "W507" not in _codes(store)


class TestAssertedSeverityStaysWithinTheChain:
    def _with_reachable_severity(self, store: Any, severity: str) -> str:
        node_id = _failure_mode(store)
        hazard = str(store.create_node("hazard", "Stale data is served"))
        loss = str(store.create_node("loss", "Wrong decision taken"))
        store.update_node(loss, attributes={"severity": severity})
        store.add_edge(node_id, hazard, "leads-to")
        store.add_edge(hazard, loss, "leads-to")
        return node_id

    def _assert_severity(self, store: Any, node_id: str, value: str) -> None:
        store.write_fmea_assessment(
            node_id=node_id, factor="severity", basis_digest="whatever",
            value=value, justification="reviewed with the safety engineer", author="analyst",
        )

    def test_asserting_above_the_worst_reachable_loss_is_a_hard_finding(self, store: Any) -> None:
        node_id = self._with_reachable_severity(store, "minor")

        self._assert_severity(store, node_id, "catastrophic")

        assert "E509" in _codes(store)

    def test_asserting_below_it_is_allowed(self, store: Any) -> None:
        """The chain may overstate what this particular failure does; that is a real judgement."""
        node_id = self._with_reachable_severity(store, "catastrophic")

        self._assert_severity(store, node_id, "minor")

        assert "E509" not in _codes(store)

    def test_asserting_the_same_value_is_allowed(self, store: Any) -> None:
        node_id = self._with_reachable_severity(store, "major")

        self._assert_severity(store, node_id, "major")

        assert "E509" not in _codes(store)


class TestAJudgementMustBeAttributable:
    def test_an_assertion_with_no_rationale_is_a_hard_finding(self, store: Any) -> None:
        """The write path refuses this, so reaching the verifier means it arrived another way —
        an import, a repair, an older build. It still must not go unreported."""
        node_id = _failure_mode(store)
        store.write_fmea_assessment(
            node_id=node_id, factor="occurrence", basis_digest="whatever",
            value="possible", justification="", author="analyst",
        )

        assert "E508" in _codes(store)

    def test_a_complete_assertion_is_not_reported(self, store: Any) -> None:
        node_id = _failure_mode(store)
        store.write_fmea_assessment(
            node_id=node_id, factor="occurrence", basis_digest="whatever",
            value="possible", justification="comparable component fails twice a year",
            author="analyst",
        )

        assert "E508" not in _codes(store)


class TestPriorityNeverOverridesAConstraint:
    def _high_priority_failure_mode(self, store: Any) -> str:
        """Catastrophic and undetected: high whatever the occurrence."""
        node_id = _failure_mode(store)
        store.register_arch_ref(node_id, "APP@1", "binds-to")
        hazard = str(store.create_node("hazard", "Unrecoverable corruption"))
        loss = str(store.create_node("loss", "Irrecoverable data loss"))
        store.update_node(loss, attributes={"severity": "catastrophic"})
        store.add_edge(node_id, hazard, "leads-to")
        store.add_edge(hazard, loss, "leads-to")
        store.write_fmea_assessment(
            node_id=node_id, factor="occurrence", basis_digest="whatever",
            value="rare", justification="never seen", author="analyst",
        )
        return node_id

    def test_an_accepted_constraint_answering_a_high_priority_failure_is_reported(
        self, store: Any
    ) -> None:
        failure_mode = self._high_priority_failure_mode(store)
        constraint = str(store.create_node("assurance-constraint", "Corruption must be prevented"))
        store.update_node(constraint, concern_class="safety", disposition="accepted")
        store.add_edge(failure_mode, constraint, "derives")

        assert "W509" in _codes(store)

    def test_a_properly_dispositioned_constraint_is_not_reported(self, store: Any) -> None:
        failure_mode = self._high_priority_failure_mode(store)
        constraint = str(store.create_node("assurance-constraint", "Corruption must be prevented"))
        store.update_node(constraint, concern_class="safety", disposition="controlled-with-evidence")
        store.add_edge(failure_mode, constraint, "derives")

        assert "W509" not in _codes(store)

    def test_an_accepted_constraint_answering_nothing_high_is_not_reported(self, store: Any) -> None:
        """The tripwire is about priority overriding an obligation, not about acceptance itself —
        acceptance on a safety constraint is already its own finding."""
        constraint = str(store.create_node("assurance-constraint", "A minor concern"))
        store.update_node(constraint, concern_class="safety", disposition="accepted")

        assert "W509" not in _codes(store)


class TestEvidenceIsNeverLessRestrictedThanWhatItEvidences:
    def test_less_restricted_evidence_is_a_hard_finding(self, store: Any) -> None:
        """The exposure policy filters per node, so nothing else prevents a reader cleared only for
        the evidence learning what the constraint says from it."""
        constraint = str(store.create_node("assurance-constraint", "Clearance is checked"))
        store.update_node(constraint, tlp="TLP:GREEN")
        evidence = str(store.create_node("evidence", "Exposure policy suite"))
        store.update_node(evidence, tlp="TLP:WHITE")
        store.add_edge(constraint, evidence, "evidenced-by")

        assert "E511" in _codes(store)

    def test_equally_restricted_evidence_is_fine(self, store: Any) -> None:
        constraint = str(store.create_node("assurance-constraint", "Clearance is checked"))
        store.update_node(constraint, tlp="TLP:GREEN")
        evidence = str(store.create_node("evidence", "Exposure policy suite"))
        store.update_node(evidence, tlp="TLP:GREEN")
        store.add_edge(constraint, evidence, "evidenced-by")

        assert "E511" not in _codes(store)

    def test_more_restricted_evidence_is_fine(self, store: Any) -> None:
        constraint = str(store.create_node("assurance-constraint", "Clearance is checked"))
        store.update_node(constraint, tlp="TLP:GREEN")
        evidence = str(store.create_node("evidence", "Exposure policy suite"))
        store.update_node(evidence, tlp="TLP:RED")
        store.add_edge(constraint, evidence, "evidenced-by")

        assert "E511" not in _codes(store)


class TestAnAnalysedElementShouldBeExamined:
    def test_a_control_structure_element_with_no_failure_modes_is_reported(self, store: Any) -> None:
        """The hazard analysis already says this element matters."""
        control_node = str(store.create_node("control-structure-node", "Assurance store"))
        store.register_arch_ref(control_node, "APP@store", "binds-to")

        assert "W510" in _codes(store)

    def test_examining_it_satisfies_the_rule(self, store: Any) -> None:
        control_node = str(store.create_node("control-structure-node", "Assurance store"))
        store.register_arch_ref(control_node, "APP@store", "binds-to")
        failure_mode = _failure_mode(store)
        store.register_arch_ref(failure_mode, "APP@store", "binds-to")

        assert "W510" not in _codes(store)
