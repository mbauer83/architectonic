"""E511 reads a record's TLP level as the exposure policy does: one carrying none ranks as TLP:RED.

Regression: the rule read a missing level as TLP:AMBER, while the exposure policy withholds such a
record from every reader below RED. Evidence at TLP:AMBER attached to a constraint with no level was
therefore passed, although an AMBER reader sees the evidence and not what it evidences.
"""

from __future__ import annotations

from src.application.verification._assurance_rules_failure_modes import check_evidence_is_not_less_restricted
from src.application.verification.assurance_issues import AssuranceVerificationResult


def _findings(evidence: dict[str, object], subject: dict[str, object]) -> list[str]:
    edges: list[dict[str, object]] = [
        {"source_id": subject["node_id"], "target_id": evidence["node_id"], "conn_type": "evidenced-by"},
    ]
    result = AssuranceVerificationResult(issues=[])
    check_evidence_is_not_less_restricted(evidence, edges, {str(subject["node_id"]): subject}, result)
    return [issue.code for issue in result.issues]


def test_evidence_below_red_for_an_unclassified_subject_is_a_finding() -> None:
    evidence: dict[str, object] = {"node_id": "E1", "node_type": "evidence", "tlp": "TLP:AMBER"}
    subject: dict[str, object] = {"node_id": "C1", "node_type": "assurance-constraint"}

    assert _findings(evidence, subject) == ["E511"]


def test_unclassified_evidence_is_as_restricted_as_anything() -> None:
    evidence: dict[str, object] = {"node_id": "E1", "node_type": "evidence"}
    subject: dict[str, object] = {"node_id": "C1", "node_type": "assurance-constraint", "tlp": "TLP:RED"}

    assert _findings(evidence, subject) == []
