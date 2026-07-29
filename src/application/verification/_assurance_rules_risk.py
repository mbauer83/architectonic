"""Verifier rules about risk entities — the optional governance overlay.

A risk assesses a hazard and records how it is being treated. These rules keep the overlay from
becoming a way to close a safety obligation: accepting a risk is a statement about appetite, not
a control, so a safety hazard needs a constraint regardless.
"""

from __future__ import annotations

from src.application.verification._assurance_rule_support import attributes_of, edges_from
from src.application.verification._assurance_rules_constraints import SAFETY_CLASSES
from src.application.verification.assurance_findings import (
    ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER,
    RISK_HAS_A_TREATMENT,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult

_ACCEPT = "accept"


def check_accepted_risk_is_not_the_whole_answer(
    risk_node: dict[str, object],
    all_nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """An accepted risk over a safety hazard must still be treated by a constraint."""
    node_id = str(risk_node["node_id"])
    if str(attributes_of(risk_node).get("treatment") or "") != _ACCEPT:
        return
    if edges_from(edges, node_id, "treated-by"):
        return
    assessed_ids = {str(e["target_id"]) for e in edges_from(edges, node_id, "assesses")}
    nodes_by_id = {str(n["node_id"]): n for n in all_nodes}
    for assessed_id in assessed_ids:
        assessed = nodes_by_id.get(assessed_id)
        if assessed is None or str(assessed.get("concern_class") or "") not in SAFETY_CLASSES:
            continue
        result.issues.append(AssuranceIssue.of(
            ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER,
            message=(
                "risk.treatment='accept' cannot be the sole disposition of a safety hazard. "
                "The risk must be treated-by at least one assurance-constraint."
            ),
            node_id=node_id,
        ))
        return


def check_has_a_treatment(
    node: dict[str, object],
    result: AssuranceVerificationResult,
) -> None:
    """A risk with no treatment says nothing about what anyone intends to do."""
    node_id = str(node["node_id"])
    if str(attributes_of(node).get("treatment") or "").strip():
        return
    result.issues.append(AssuranceIssue.of(
        RISK_HAS_A_TREATMENT,
        message="Risk has no 'treatment' attribute. Set to: mitigate | transfer | avoid | accept.",
        node_id=node_id,
    ))
