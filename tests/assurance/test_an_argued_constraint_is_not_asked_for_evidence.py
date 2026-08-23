"""A constraint answered by argument is not asked to produce evidence of a control.

Two rules read the same constraint and disagreed about it. **W501** accepts a constraint that states
no means of enforcement provided it records an `enforcement_justification` — the author has said there
is no control and why. **W502** then asks the same constraint for `evidenced-by`, which is evidence
that a control works.

For `alarp-justified` that is unanswerable by construction, and the vocabulary says so itself: ALARP
means *residual exposure remains and is argued to be as low as reasonably practicable*, while
`controlled-with-evidence` is the one whose meaning reads *claiming this requires that evidence*. So
W502 was asking for the artefact the chosen disposition declares absent, and the only way to silence
it would be to attach evidence of a control that does not exist.

The shipped store has one: a constraint asking that a deployment be able to enumerate the assurance
bridges it has granted, dispositioned `alarp-justified` because the platform holds no record of its
grants — the justification names that gap in full and calls it the weakest link in the access path.
A warning against it trains a reader to skip W502, which is the cost the analysis can least afford.

**Narrow on purpose.** The exemption needs *both* the argument-shaped disposition and a recorded
justification. `alarp-justified` with nothing written is an empty claim, and W501 already fires on
exactly that; requiring both means a constraint escapes W502 only where the argument is present and
readable. Every other disposition still owes evidence, including a constraint with none decided yet.
"""

from __future__ import annotations

from typing import Any

from src.application.verification._assurance_rules_constraints import check_has_evidence
from src.application.verification.assurance_issues import AssuranceVerificationResult


def _constraint(**attrs: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "node_id": "ACN@1000000000.aaaa.000001",
        "node_type": "assurance-constraint",
        "concern_class": "security",
        "attributes_json": "{}",
    }
    node.update(attrs)
    return node


def _codes(node: dict[str, Any]) -> list[str]:
    result = AssuranceVerificationResult()
    check_has_evidence(node, [], frozenset(), result)
    return [issue.code for issue in result.issues]


ARGUED = '{"enforcement_justification": "The platform holds no record of its grants."}'


class TestAConstraintAnsweredByArgument:
    def test_it_is_not_asked_for_evidence(self) -> None:
        node = _constraint(disposition="alarp-justified", attributes_json=ARGUED)

        assert _codes(node) == []


class TestWhoStillOwesEvidence:
    def test_a_controlled_constraint_does(self) -> None:
        """Its disposition's own meaning is that claiming it requires the evidence."""
        node = _constraint(disposition="controlled-with-evidence", attributes_json=ARGUED)

        assert _codes(node) == ["W502"]

    def test_an_argued_constraint_with_no_argument_written_does(self) -> None:
        """The disposition alone is a label. Without the justification there is nothing to read
        instead of evidence, and W501 is already objecting to the same emptiness."""
        node = _constraint(disposition="alarp-justified")

        assert _codes(node) == ["W502"]

    def test_a_constraint_with_no_disposition_does(self) -> None:
        """Nothing decided yet is not an argument that nothing is needed."""
        node = _constraint(attributes_json=ARGUED)

        assert _codes(node) == ["W502"]

    def test_an_accepted_constraint_does(self) -> None:
        """Accepting is how an obligation gets priced away; it buys no exemption."""
        node = _constraint(disposition="accepted", attributes_json=ARGUED)

        assert _codes(node) == ["W502"]

    def test_a_constraint_designed_out_does(self) -> None:
        """`prevented-by-design` claims the outcome is structurally impossible, which is a claim
        about the design that a reader can be shown. Deliberately not exempted."""
        node = _constraint(disposition="prevented-by-design", attributes_json=ARGUED)

        assert _codes(node) == ["W502"]


class TestTheDomainStatesWhichDispositionsArgue:
    def test_alarp_answers_by_argument(self) -> None:
        from src.domain.assurance.constraint_dispositions import answers_by_argument

        assert answers_by_argument("alarp-justified")

    def test_controlled_with_evidence_does_not(self) -> None:
        from src.domain.assurance.constraint_dispositions import answers_by_argument

        assert not answers_by_argument("controlled-with-evidence")

    def test_an_unknown_value_does_not(self) -> None:
        """A value this software does not know is not thereby an argument — the same restraint
        `rank` applies to an unrecognised disposition."""
        from src.domain.assurance.constraint_dispositions import answers_by_argument

        assert not answers_by_argument("no-such-disposition")
