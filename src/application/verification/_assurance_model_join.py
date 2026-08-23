"""Where the verifier joins the assurance store to the architecture graph.

Kept out of the verifier itself because the join is a distinct concern with its own reason to
change — which reference type binds an element, how an occurrence rationale's citations are
assembled — and because the verifier is at its length budget.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.application.assurance.fmea_occurrence_evidence import (
    ElementSecurityBasis,
    occurrence_evidence,
)
from src.application.assurance.node_attributes import attribute
from src.application.assurance.ports import ConfidentialAssuranceStore
from src.application.verification.assurance_issues import (
    AssuranceIssue,
    AssuranceVerificationResult,
)
from src.application.verification.assurance_two_way_coverage import two_way_findings
from src.domain.artifact_id import canonical_entity_key

BINDS_TO = "binds-to"
FAILURE_MODE = "failure-mode"
CONTROL_STRUCTURE_NODE = "control-structure-node"


def bound_elements(store: ConfidentialAssuranceStore) -> Mapping[str, str]:
    """Which architecture element each assurance node is bound to, canonically keyed.

    Read once for the whole verification rather than per node: every failure-mode rule that needs
    the graph needs this same mapping, and the reference list does not change mid-run.
    """
    return {
        str(ref["assurance_node_id"]): canonical_entity_key(str(ref.get("arch_artifact_id") or ""))
        for ref in store.list_arch_refs()
        if str(ref.get("ref_type")) == BINDS_TO
    }


def occurrence_basis(
    node: Mapping[str, object],
    element_id: str,
    *,
    basis: ArchitectureBasis,
    security: Mapping[str, ElementSecurityBasis],
) -> tuple[str, ...] | None:
    """What a judgement about this failure mode's occurrence would have cited, or None if unknowable.

    Recomputed here rather than stored, so it is by construction the *current* picture. A recorded
    judgement carries the digest of the picture it was made against; comparing the two is what
    tells a reader the judgement has stopped applying.

    `None` where the basis was never assembled, which is not the same as assembled and citing
    nothing: the first cannot ground a judgement at all, and returning an empty tuple for it is how
    eleven judgements came to be recorded against a hash that retired them on sight.
    """
    if not basis.assembled:
        return None
    element_security = security.get(element_id, ElementSecurityBasis())
    return occurrence_evidence(
        element_id,
        concern_class=str(attribute(node, "concern_class") or node.get("concern_class") or ""),
        edges=basis.edges,
        connections=basis.connections,
        entities=basis.entities,
        vulnerability_ids=element_security.vulnerability_ids,
        sbom_anchored=bool(element_security.vulnerability_ids),
        security_basis_snapshot_id=element_security.snapshot_id,
    ).basis


def append_two_way_findings(
    *,
    all_nodes: Sequence[Mapping[str, object]],
    element_by_node: Mapping[str, str],
    basis: ArchitectureBasis,
    severity_by_element: Mapping[str, str],
    result: AssuranceVerificationResult,
) -> None:
    """Run the checks that need both models and record what they find.

    `analysed_element_ids` counts an element as analysed when *any* assurance node binds to it, not
    only a control-structure node: an element someone has already written failure modes against is
    plainly not overlooked, and reporting it as an analysis gap would train readers to ignore the
    finding.
    """
    analysed = frozenset(
        element for node_id, element in element_by_node.items()
        if element and node_id in {str(n["node_id"]) for n in all_nodes}
    )
    for finding in two_way_findings(
        basis=basis,
        analysed_element_ids=analysed,
        severity_by_element=severity_by_element,
    ):
        result.issues.append(AssuranceIssue.of(
            finding.kind, message=finding.message, node_id=finding.subject_id,
            witness=finding.witness, subject_name=finding.subject_name,
        ))
