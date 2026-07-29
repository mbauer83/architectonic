"""Verifier rules about the causal chain and its coverage.

The chain runs unsafe control action → hazard → loss, with an incident investigating what
happened and an obligation reaching the constraints that comply with it. A break anywhere means
an analysis that cannot say what it is about, so each rule names the missing link rather than
the missing field.
"""

from __future__ import annotations

from src.application.verification._assurance_rule_support import edges_from, edges_into
from src.application.verification.assurance_findings import (
    CONTROL_NODE_IS_BOUND,
    HAZARD_REACHES_A_LOSS,
    INCIDENT_INVESTIGATES_SOMETHING,
    OBLIGATION_REACHES_A_CONSTRAINT,
    UCA_NAMES_ONE_CONTROL_ACTION,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult


def check_uca_names_one_control_action(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """An unsafe control action is unsafe *about* one control action; naming none or several
    leaves it unclear which control the finding constrains."""
    node_id = str(node["node_id"])
    concerns = edges_from(edges, node_id, "concerns")
    if len(concerns) == 1:
        return
    message = (
        "UCA must reference exactly one control-action via a 'concerns' edge."
        if not concerns
        else f"UCA must reference exactly ONE control-action; found {len(concerns)}."
    )
    result.issues.append(AssuranceIssue.of(
        UCA_NAMES_ONE_CONTROL_ACTION, message=message, node_id=node_id,
    ))


def check_hazard_reaches_a_loss(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """A hazard with no loss states a condition without saying why it matters."""
    node_id = str(node["node_id"])
    if edges_from(edges, node_id, "leads-to"):
        return
    result.issues.append(AssuranceIssue.of(
        HAZARD_REACHES_A_LOSS,
        message="Hazard has no 'leads-to' connection to a loss. Connect it to complete the STPA chain.",
        node_id=node_id,
    ))


def check_incident_investigates_something(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """An incident that names nothing it investigates records an event but no analysis."""
    node_id = str(node["node_id"])
    if edges_from(edges, node_id, "investigates"):
        return
    result.issues.append(AssuranceIssue.of(
        INCIDENT_INVESTIGATES_SOMETHING,
        message=(
            "CAST incident has no 'investigates' edge. "
            "Connect it to a control-structure-node or hazard."
        ),
        node_id=node_id,
    ))


def check_obligation_reaches_a_constraint(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """An obligation nothing complies with is a compliance gap, not a satisfied requirement."""
    node_id = str(node["node_id"])
    if edges_into(edges, node_id, "complies-with"):
        return
    result.issues.append(AssuranceIssue.of(
        OBLIGATION_REACHES_A_CONSTRAINT,
        message="Obligation has no 'complies-with' constraint. Link one to close the compliance gap.",
        node_id=node_id,
    ))


def check_control_node_is_bound(
    node: dict[str, object],
    result: AssuranceVerificationResult,
) -> None:
    """An unbound control-structure node names a part of the system the model does not hold."""
    node_id = str(node["node_id"])
    if str(node.get("binding_status") or "") != "unbound-pending":
        return
    result.issues.append(AssuranceIssue.of(
        CONTROL_NODE_IS_BOUND,
        message=(
            "control-structure-node has binding_status='unbound-pending': "
            "this node is not linked to an architecture entity. "
            "Consider using the 'model this' workflow to bind it."
        ),
        node_id=node_id,
    ))
