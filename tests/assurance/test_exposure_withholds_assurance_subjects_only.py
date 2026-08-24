"""The exposure filter withholds assurance content, not findings about the architecture model.

`redact_verification` kept an issue when its `node_id` was among the *visible assurance node ids*, and
dropped it otherwise. Every coverage finding names an **architecture element** as its subject — that is
what it is about — and an architecture element id is never an assurance node id. So the whole two-way
coverage half was withheld from REST and from the GUI, silently, from a reader who was entitled to all
of it.

Measured on the shipped store: **17 of 20** issues dropped, every one a W511, leaving only the three
W507s whose subject is an assurance node. The findings were computed, counted, and then removed.

The rule the filter meant to state is already in its own docstring — *an issue naming no node is about
the store itself and stays, there is no subject to withhold*. An issue naming something that is not an
assurance node is the same case: there is no assurance subject to withhold. So it withholds only where
the subject **is** an assurance node this reader may not see, which needs the full node set to tell
"not an assurance node" from "an assurance node held back".

**Loosening a confidentiality filter deserves the argument spelled out.** A coverage finding discloses
architecture facts, which carry no TLP, and the *absence* of assurance content. It cannot disclose
withheld content by inference either: the finding is computed over the whole store, so it fires only
where genuinely nothing is bound — an element analysed by a node above the ceiling produces no finding
at all, and its silence tells a low-clearance reader nothing.
"""

from __future__ import annotations

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.verification.assurance_findings import (
    CONSTRAINT_HAS_EVIDENCE,
    LOAD_BEARING_ELEMENT_IS_ANALYSED,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult

VISIBLE_NODE = "ACN@1000000000.aaaa.000001"
WITHHELD_NODE = "ACN@1000000000.bbbb.000002"
ARCHITECTURE_ELEMENT = "AIF@1712870400.KxvY-B"


def _result() -> AssuranceVerificationResult:
    result = AssuranceVerificationResult()
    result.issues.extend([
        AssuranceIssue.of(CONSTRAINT_HAS_EVIDENCE, message="visible subject", node_id=VISIBLE_NODE),
        AssuranceIssue.of(CONSTRAINT_HAS_EVIDENCE, message="withheld subject", node_id=WITHHELD_NODE),
        AssuranceIssue.of(
            LOAD_BEARING_ELEMENT_IS_ANALYSED, message="load-bearing", node_id=ARCHITECTURE_ELEMENT,
        ),
        AssuranceIssue.of(CONSTRAINT_HAS_EVIDENCE, message="about the store", node_id=""),
    ])
    return result


def _redacted(policy: AssuranceExposurePolicy) -> list[str]:
    kept = policy.redact_verification(
        _result(),
        frozenset({VISIBLE_NODE}),
        known_node_ids=frozenset({VISIBLE_NODE, WITHHELD_NODE}),
    )
    return [issue.message for issue in kept.issues]


class TestWhatSurvives:
    def test_a_finding_about_an_architecture_element_survives(self) -> None:
        """The 17 that were being dropped."""
        assert "load-bearing" in _redacted(AssuranceExposurePolicy("TLP:GREEN", True))

    def test_a_finding_about_a_visible_node_survives(self) -> None:
        assert "visible subject" in _redacted(AssuranceExposurePolicy("TLP:GREEN", True))

    def test_a_finding_about_the_store_itself_survives(self) -> None:
        assert "about the store" in _redacted(AssuranceExposurePolicy("TLP:GREEN", True))


class TestWhatIsStillWithheld:
    def test_a_finding_about_a_node_above_the_ceiling_is_withheld(self) -> None:
        """The whole purpose of the filter, unchanged."""
        assert "withheld subject" not in _redacted(AssuranceExposurePolicy("TLP:GREEN", True))

    def test_the_counts_come_from_what_survived(self) -> None:
        """Recounting beside the filter is how a response says `valid: false` with no visible error."""
        policy = AssuranceExposurePolicy("TLP:GREEN", True)
        kept = policy.redact_verification(
            _result(),
            frozenset({VISIBLE_NODE}),
            known_node_ids=frozenset({VISIBLE_NODE, WITHHELD_NODE}),
        )

        assert len(kept.issues) == 3


class TestWithoutTheFullNodeSet:
    def test_it_falls_back_to_withholding_every_unknown_subject(self) -> None:
        """A caller that cannot say which ids are assurance nodes gets the old, closed behaviour
        rather than an opened filter: this is a confidentiality boundary, so the default fails shut."""
        policy = AssuranceExposurePolicy("TLP:GREEN", True)
        kept = policy.redact_verification(_result(), frozenset({VISIBLE_NODE}))

        assert [issue.message for issue in kept.issues] == ["visible subject", "about the store"]
