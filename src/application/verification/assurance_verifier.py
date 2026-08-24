"""Assurance verifier — hard structural validity rules over the confidential store.

Separate from the architecture ArtifactVerifier: this operates on the
ConfidentialAssuranceStore rather than on git-backed files. Codes and their severities are
declared in `assurance_findings`; the rules themselves live in sibling modules grouped by the
concern they check, and this module reads the store once and dispatches them.

Reading once matters: every rule needs the same node list, edge list and architecture
references, and a rule that fetched its own would turn one verification into many queries.

Writes are never blocked by these findings — a hard finding blocks sign-off, which is a
different gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.application.assurance.fmea_occurrence_evidence import ElementSecurityBasis
from src.application.verification import _assurance_rules_chain as chain
from src.application.verification import _assurance_rules_constraints as constraints
from src.application.verification import _assurance_rules_failure_modes as failures
from src.application.verification import _assurance_rules_risk as risk
from src.application.verification._assurance_failure_mode_context import (
    read_failure_mode_context,
)
from src.application.verification._assurance_model_join import append_two_way_findings
from src.application.verification.assurance_findings import EDGE_ENDPOINTS_RESOLVE, STORE_LOCKED
from src.application.verification.assurance_issues import (
    AssuranceIssue,
    AssuranceVerificationResult,
    SeverityLiteral,
)
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.assurance_node_types import CONTROL_STRUCTURE_NODE

if TYPE_CHECKING:
    from src.application.assurance.ports import ConfidentialAssuranceStore

__all__ = [
    "AssuranceIssue",
    "AssuranceVerificationResult",
    "SeverityLiteral",
    "format_result",
    "verify_store",
]


def _check_edge_endpoints_resolve(
    all_nodes: list[dict[str, object]],
    all_edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """An edge whose source or target no longer exists. Navigation surfaces omit such edges
    silently — indistinguishable from a hidden endpoint — so the verifier is deliberately the
    only place they become visible."""
    node_ids = {str(n["node_id"]) for n in all_nodes}
    for edge in all_edges:
        source_id = str(edge["source_id"])
        target_id = str(edge["target_id"])
        missing = [nid for nid in (source_id, target_id) if nid not in node_ids]
        if not missing:
            continue
        present = source_id if source_id in node_ids else target_id if target_id in node_ids else ""
        result.issues.append(AssuranceIssue.of(
            EDGE_ENDPOINTS_RESOLVE,
            message=(
                f"Edge {edge['edge_id']} ({edge['conn_type']}) references "
                f"nonexistent node(s): {', '.join(missing)}. Delete the edge or restore the node."
            ),
            node_id=present,
        ))


def _arch_ref_node_ids(store: ConfidentialAssuranceStore, ref_type: str) -> frozenset[str]:
    """Read-only membership set — frozen so a rule cannot mutate what a sibling rule reads."""
    return frozenset(
        str(ref["assurance_node_id"])
        for ref in store.list_arch_refs()
        if str(ref.get("ref_type")) == ref_type
    )


def verify_store(
    store: ConfidentialAssuranceStore,
    *,
    basis: ArchitectureBasis = ArchitectureBasis(),
    security: Mapping[str, ElementSecurityBasis] | None = None,
) -> AssuranceVerificationResult:
    """Run every structural and informational check over the whole store.

    `basis` is the architecture graph. Without it the store-only checks all run and the three
    that compare the two models are skipped — they have no question to ask, not a silent pass.
    """
    result = AssuranceVerificationResult()
    if not store.is_unlocked():
        result.issues.append(AssuranceIssue.of(
            STORE_LOCKED,
            message="Assurance store is locked. Run `arch-assurance unlock` to verify.",
        ))
        return result

    all_nodes = store.list_nodes()
    all_edges = store.list_edges()
    evidenced = _arch_ref_node_ids(store, "evidenced-by-artifact")
    refines_requirement = _arch_ref_node_ids(store, "refines-requirement")
    bound = _arch_ref_node_ids(store, "binds-to")
    nodes_by_id = {str(node["node_id"]): node for node in all_nodes}
    failure_modes = read_failure_mode_context(
        store, all_nodes, all_edges, basis=basis, security=security or {},
    )

    _check_edge_endpoints_resolve(all_nodes, all_edges, result)

    for node in all_nodes:
        node_type = str(node.get("node_type", ""))

        if node_type == "unsafe-control-action":
            chain.check_uca_names_one_control_action(node, all_edges, result)
        elif node_type == "assurance-constraint":
            constraints.check_has_responsible_controller(node, all_edges, result)
            constraints.check_not_merely_accepted(node, result)
            constraints.check_is_enforced_or_justified(node, refines_requirement, result)
            constraints.check_has_evidence(node, all_edges, evidenced, result)
            failures.check_priority_does_not_override_a_constraint(
                node, all_edges, failure_modes.high_priority_ids, result,
            )
        elif node_type == "risk":
            risk.check_accepted_risk_is_not_the_whole_answer(node, all_nodes, all_edges, result)
            risk.check_has_a_treatment(node, result)
        elif node_type == CONTROL_STRUCTURE_NODE:
            chain.check_control_node_is_bound(node, result)
        elif node_type == "hazard":
            chain.check_hazard_reaches_a_loss(node, all_edges, result)
        elif node_type == "incident":
            chain.check_incident_investigates_something(node, all_edges, result)
        elif node_type == "obligation":
            chain.check_obligation_reaches_a_constraint(node, all_edges, result)
        elif node_type == "evidence":
            failures.check_evidence_is_not_less_restricted(node, all_edges, nodes_by_id, result)
        elif node_type == failures.FAILURE_MODE:
            failures.check_failure_mode_is_bound(node, bound, result)
            failures.check_reaches_a_hazard(node, all_edges, result)
            failures.check_has_a_detection_control(node, all_edges, result)
            node_id = str(node["node_id"])
            failures.check_factor_assertions(
                node,
                failure_modes.assessments.get(node_id, ()),
                failure_modes.derived_severity.get(node_id),
                failure_modes.digests.get(node_id, {}),
                result,
            )

    _check_analysed_elements_are_examined(store, all_nodes, result)
    append_two_way_findings(
        all_nodes=all_nodes,
        element_by_node=failure_modes.element_by_node,
        basis=basis,
        severity_by_element=failure_modes.severity_by_element,
        result=result,
    )
    return result


def _check_analysed_elements_are_examined(
    store: ConfidentialAssuranceStore,
    all_nodes: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """Elements the control structure names that no failure mode has examined."""
    refs = store.list_arch_refs()
    by_element: dict[str, list[str]] = {}
    failure_mode_elements: set[str] = set()
    node_types = {str(node["node_id"]): str(node.get("node_type", "")) for node in all_nodes}
    for ref in refs:
        if str(ref.get("ref_type")) != "binds-to":
            continue
        node_id = str(ref["assurance_node_id"])
        # Stable form on both sides of the join. A control-structure node bound by the full id
        # and a failure mode bound by the short one describe the same element; compared raw, the
        # finding is reported once per spelling and no amount of analysis silences it.
        element_id = canonical_entity_key(str(ref["arch_artifact_id"]))
        if node_types.get(node_id) == CONTROL_STRUCTURE_NODE:
            by_element.setdefault(element_id, []).append(node_id)
        elif node_types.get(node_id) == failures.FAILURE_MODE:
            failure_mode_elements.add(element_id)
    for element_id, control_nodes in sorted(by_element.items()):
        if element_id in failure_mode_elements:
            continue
        failures.check_analysed_element_has_failure_modes(element_id, control_nodes, result)


def format_result(result: AssuranceVerificationResult) -> dict[str, object]:
    return {
        "valid": result.valid,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "info_count": len(result.informational),
        "issues": [
            {
                "severity": i.severity, "code": i.code, "message": i.message, "node_id": i.node_id,
                # Sent even when empty, so a reader never has to distinguish "no evidence carried"
                # from "this response predates evidence being carried".
                "witness": list(i.witness),
                # Sent even when empty, for the same reason as the witness: a reader must not have to
                # tell "no name available" from "this response predates names being carried".
                "subject_name": i.subject_name,
            }
            for i in result.issues
        ],
    }
