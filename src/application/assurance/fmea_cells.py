"""One cell of the failure-mode matrix: which of three states it is in, and what it says.

Split from the matrix assembly because the two answer different questions. Assembly decides *which*
(element, guideword) pairs a reader is offered; this decides what one of them reports once offered —
its factors, whether occurrence could still change the band, and what to do next about it.

**Every cell reports which of three states it is in**, because two states would leave an empty cell
meaning either "nobody looked" or "someone looked and found nothing" — and an unstarted analysis
would then be indistinguishable from a complete one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.application.assurance.fmea_derivation import derive_factors
from src.application.assurance.fmea_occurrence_evidence import (
    ElementSecurityBasis,
    OccurrenceEvidence,
    occurrence_evidence,
)
from src.application.assurance.node_attributes import attribute
from src.domain.assurance.failure_modes import NOT_CREDIBLE, RECORDED, UNTOUCHED
from src.domain.assurance.fmea_action_priority import INDETERMINATE, action_priority, occurrence_is_decisive
from src.domain.assurance.fmea_factors import (
    DETECTABILITY,
    FMEA_FACTORS,
    OCCURRENCE,
    SEVERITY,
    EffectiveFactor,
    FactorAssessment,
    effective_factor,
)


@dataclass(frozen=True)
class Cell:
    """One (element, guideword) pair."""

    element_id: str
    guideword: str
    state: str
    node_id: str | None = None
    factors: Mapping[str, EffectiveFactor] = field(default_factory=dict)
    basis_digests: Mapping[str, str] = field(default_factory=dict)
    """Per factor, the digest of the model inputs its derived value came from. Published because a
    judgement applies only while its basis still holds, so a caller recording one has to send the
    digest back — and without it here there is nowhere to read it from. An assessment filed against
    a digest that never matched is retained but never applies, which for occurrence (asserted-only,
    with no derived value to fall back to) means the row stays undecidable however carefully it was
    judged."""
    occurrence_rationale_draft: str = ""
    """What the model already knows about this element, for a rationale someone is about to write.
    Facts only — nothing here proposes a rank."""
    action_priority: str = INDETERMINATE
    occurrence_is_requested: bool = False
    """False where occurrence cannot change the band, so the field is not rendered at all."""
    next_action: str = ""
    dismissal: Mapping[str, str] = field(default_factory=dict)



def next_action(cell_state: str, factors: Mapping[str, EffectiveFactor], priority: str) -> str:
    """The one thing that would advance this row, in the analyst's words.

    Generated from the same conditions the verifier reports, so a reader never has to map a finding
    code back to a row. One source, two renderings.
    """
    if cell_state == UNTOUCHED:
        return "Examine this guideword: record a failure mode, or dismiss it as not credible."
    if cell_state == NOT_CREDIBLE:
        return ""
    if factors.get(SEVERITY) is not None and factors[SEVERITY].value is None:
        return "Link an effect to a hazard, so severity can be derived."
    if factors.get(DETECTABILITY) is not None and factors[DETECTABILITY].value == "very-low":
        return "Nothing detects this failure — add a detection control, or accept the worst band."
    if priority == INDETERMINATE and factors.get(OCCURRENCE) is not None and factors[OCCURRENCE].value is None:
        return "Record an occurrence with a rationale; the band cannot be decided without it."
    return ""


def _occurrence_evidence_for(
    element_id: str,
    node: Mapping[str, object],
    *,
    basis: ArchitectureBasis,
    security: ElementSecurityBasis,
) -> OccurrenceEvidence:
    """What the model can already tell whoever is about to judge this cell's occurrence.

    Assembled per cell rather than per element because the concern class is a property of the
    failure mode, and it decides whether security signals belong in the rationale at all.
    """
    return occurrence_evidence(
        element_id,
        concern_class=str(attribute(node, "concern_class") or node.get("concern_class") or ""),
        edges=basis.edges,
        connections=basis.connections,
        entities=basis.entities,
        vulnerability_ids=security.vulnerability_ids,
        sbom_anchored=bool(security.vulnerability_ids),
        security_basis_snapshot_id=security.snapshot_id,
    )


def cell_for(
    element_id: str,
    guideword: str,
    node: Mapping[str, object] | None,
    *,
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
    assessments: Mapping[str, Sequence[FactorAssessment]],
    basis: ArchitectureBasis = ArchitectureBasis(),
    security: ElementSecurityBasis = ElementSecurityBasis(),
) -> Cell:
    if node is None:
        return Cell(
            element_id=element_id,
            guideword=guideword,
            state=UNTOUCHED,
            next_action=next_action(UNTOUCHED, {}, INDETERMINATE),
        )
    node_id = str(node["node_id"])
    state = str(attribute(node, "assessment_state") or RECORDED)
    if state == NOT_CREDIBLE:
        return Cell(
            element_id=element_id,
            guideword=guideword,
            state=NOT_CREDIBLE,
            node_id=node_id,
            dismissal={
                "by": str(attribute(node, "dismissed_by") or ""),
                "reason": str(attribute(node, "dismissal_rationale") or ""),
            },
        )
    evidence = _occurrence_evidence_for(element_id, node, basis=basis, security=security)
    derived = derive_factors(
        node_id, nodes=nodes, edges=edges, occurrence_basis=evidence.basis,
    )
    rows = list(assessments.get(node_id, ()))
    derived_values = {
        SEVERITY: derived.severity.value,
        DETECTABILITY: derived.detectability.value,
        OCCURRENCE: None,
    }
    factors = {
        factor: effective_factor(
            factor,
            assessments=[a for a in rows if a.factor == factor],
            derived_value=derived_values[factor],
            current_basis_digest=derived.digests[factor],
        )
        for factor in FMEA_FACTORS
    }
    priority = action_priority(
        factors[SEVERITY].value, factors[OCCURRENCE].value, factors[DETECTABILITY].value,
    )
    # Asked for only where it could change the band. Both inputs are derived, so the answer is
    # known before anyone is asked; where either is absent the question cannot be settled yet, so
    # the field is offered rather than suppressed.
    severity_value = factors[SEVERITY].value
    detectability_value = factors[DETECTABILITY].value
    requested = (
        severity_value is None
        or detectability_value is None
        or occurrence_is_decisive(severity_value, detectability_value)
    )
    return Cell(
        element_id=element_id,
        guideword=guideword,
        state=RECORDED,
        node_id=node_id,
        factors=factors,
        basis_digests=dict(derived.digests),
        occurrence_rationale_draft=evidence.rationale_draft(),
        action_priority=priority,
        occurrence_is_requested=requested,
        next_action=next_action(RECORDED, factors, priority),
    )



def cell_payload(cell: Cell) -> dict[str, object]:
    return {
        "guideword": cell.guideword,
        "state": cell.state,
        "node_id": cell.node_id,
        "action_priority": cell.action_priority,
        "occurrence_is_requested": cell.occurrence_is_requested,
        # Facts, never a value: the drafted rationale is what the model already knows, offered to
        # whoever is about to judge. Nothing here suggests a rank.
        "occurrence_rationale_draft": cell.occurrence_rationale_draft,
        "next_action": cell.next_action,
        "dismissal": dict(cell.dismissal),
        "factors": {
            name: {
                "value": factor.value,
                "basis": factor.basis,
                "basis_digest": cell.basis_digests.get(name, ""),
                "superseded": None if factor.superseded_assessment is None else {
                    "value": factor.superseded_assessment.value,
                    "author": factor.superseded_assessment.author,
                    "justification": factor.superseded_assessment.justification,
                },
            }
            for name, factor in cell.factors.items()
        },
    }
