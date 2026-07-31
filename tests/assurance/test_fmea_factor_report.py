"""A failure mode's factor report — the read a factor judgement cannot be made without.

`assurance_set_fmea_factor` refuses a judgement with no `basis_digest`, and a judgement applies only
while that digest still matches the model inputs its derived value came from. The digest is computed,
never chosen, so a caller has to read it from somewhere — and through MCP there was nowhere: the
matrix is a REST/GUI surface, and `assurance_read_node` returned a failure mode without its factors.

Occurrence is what makes that a blocker rather than an inconvenience. It is asserted-only, with no
derived value to fall back on, so a judgement filed against a digest that never matched is retained
and never applies, and the row stays undecidable however carefully it was judged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_fmea_lens import factor_report

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

ELEMENT = "APP@1777293133.OYEmP1"


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    # Every node records the analysis that produced it; one without provenance is repair-only, so a
    # fixture minting an unattributed node would exercise that guard rather than the report.
    analysis = str(built.create_analysis("Fixture analysis", "FMEA", tlp="TLP:WHITE"))
    built._fixture_analysis = analysis  # noqa: SLF001 — the fixture's own handle on its analysis
    controller = str(built.create_node(
        "control-structure-node", "Controller", analysis_id=analysis,
    ))
    built.register_arch_ref(controller, ELEMENT, "binds-to")
    yield built
    built.lock()


def _failure_mode(store: Any, *, with_hazard: bool = True) -> str:
    analysis = store._fixture_analysis  # noqa: SLF001
    node_id = str(store.create_node(
        "failure-mode", "Serves a result before the clearance check runs",
        failure_type="partial-function", analysis_id=analysis,
    ))
    store.register_arch_ref(node_id, ELEMENT, "binds-to")
    if with_hazard:
        loss = str(store.create_node("loss", "Disclosure", analysis_id=analysis))
        store.update_node(loss, attributes={"severity": "major"})
        hazard = str(store.create_node(
            "hazard", "Readable outside the gate", analysis_id=analysis,
        ))
        store.add_edge(node_id, hazard, "leads-to")
        store.add_edge(hazard, loss, "leads-to")
    return node_id


def _report(store: Any, node_id: str) -> dict[str, object]:
    policy = AssuranceExposurePolicy("TLP:RED", True)
    visible, _ = policy.filter_nodes(store.list_nodes())
    found = factor_report(node_id, store=store, policy=policy, nodes=visible)
    assert found is not None
    return found


class TestTheReportCarriesWhatAJudgementNeeds:
    def test_every_factor_publishes_a_basis_digest(self, store: Any) -> None:
        report = _report(store, _failure_mode(store))
        factors = report["factors"]
        assert isinstance(factors, dict)

        for name in ("severity", "occurrence", "detectability"):
            assert factors[name]["basis_digest"], f"{name} publishes no digest to record against"

    def test_it_says_whether_an_occurrence_is_even_being_asked_for(self, store: Any) -> None:
        """Where occurrence cannot change the band the field is not offered, and a caller that
        asserted one anyway would be answering a question nobody asked."""
        report = _report(store, _failure_mode(store))

        assert isinstance(report["occurrence_is_requested"], bool)

    def test_it_names_the_next_action(self, store: Any) -> None:
        report = _report(store, _failure_mode(store))

        assert isinstance(report["next_action"], str)

    def test_it_reports_the_element_and_guideword_the_row_belongs_to(self, store: Any) -> None:
        report = _report(store, _failure_mode(store))

        assert report["element_id"] == ELEMENT
        assert report["guideword"] == "partial-function"


class TestRecordingAgainstThePublishedDigestApplies:
    def test_an_occurrence_recorded_against_it_becomes_the_effective_value(self, store: Any) -> None:
        """The end-to-end contract: read the digest, record against it, and the judgement holds."""
        from src.application.assurance_fmea_factors import RecordFactorRequest, record_factor_assessment

        node_id = _failure_mode(store)
        factors = _report(store, node_id)["factors"]
        assert isinstance(factors, dict)

        record_factor_assessment(
            RecordFactorRequest(
                node_id=node_id,
                factor="occurrence",
                value="unlikely",
                justification="one report in two years of operation",
                author="analyst",
                basis_digest=str(factors["occurrence"]["basis_digest"]),
            ),
            store=store,
            archive=_NullArchive(),  # type: ignore[arg-type]
        )

        after = _report(store, node_id)["factors"]
        assert isinstance(after, dict)
        assert after["occurrence"]["value"] == "unlikely"
        assert after["occurrence"]["basis"] == "asserted"

    def test_a_judgement_against_a_made_up_digest_never_applies(self, store: Any) -> None:
        """Why the digest cannot be invented when a caller has no way to read it."""
        from src.application.assurance_fmea_factors import RecordFactorRequest, record_factor_assessment

        node_id = _failure_mode(store)
        record_factor_assessment(
            RecordFactorRequest(
                node_id=node_id, factor="occurrence", value="unlikely",
                justification="one report in two years", author="analyst",
                basis_digest="not-a-real-digest",
            ),
            store=store,
            archive=_NullArchive(),  # type: ignore[arg-type]
        )

        after = _report(store, node_id)["factors"]
        assert isinstance(after, dict)
        assert after["occurrence"]["value"] is None
        assert after["occurrence"]["basis"] == "absent"


class TestAnUnboundFailureModeHasNoRow:
    def test_no_report_without_an_element(self, store: Any) -> None:
        """A failure mode names the thing that fails; unbound, there is no row to report on."""
        node_id = str(store.create_node(
            "failure-mode", "Unbound", failure_type="no-function",
            analysis_id=store._fixture_analysis,  # noqa: SLF001
        ))
        policy = AssuranceExposurePolicy("TLP:RED", True)
        visible, _ = policy.filter_nodes(store.list_nodes())

        assert factor_report(node_id, store=store, policy=policy, nodes=visible) is None


class _NullArchive:
    def append(self, *_args: object, **_kwargs: object) -> None:
        return None
