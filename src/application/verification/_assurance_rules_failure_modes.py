"""Verifier rules about failure modes: attachment, attribution, and priority discipline.

Two of these guard against a specific way the method can go wrong rather than against a modelling
slip.

`E509` bounds an asserted severity by the worst loss the failure mode actually reaches. Lowering a
derived severity with a rationale is legitimate — the chain may overstate what this particular
failure does. Raising it above every reachable loss is not: it invents consequence the model does
not contain, and then that number drives a priority.

`W509` is the anti-subordination tripwire. A priority band may never close, weaken, defer or justify
the disposition of a safety or security constraint, and the shape that violation takes is a
constraint carried as merely accepted while a failure mode it answers is high priority. The rule
exists because the pressure to price away an obligation is real and arrives as a plausible argument.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.verification._assurance_rule_support import (
    attributes_of,
    edges_from,
    edges_into,
)
from src.application.verification.assurance_findings import (
    ANALYSED_ELEMENT_HAS_FAILURE_MODES,
    ASSERTED_FACTOR_IS_ATTRIBUTABLE,
    ASSERTED_SEVERITY_STAYS_WITHIN_THE_LOSSES,
    EVIDENCE_IS_NOT_LESS_RESTRICTED,
    FACTOR_JUDGEMENT_STILL_APPLIES,
    FAILURE_MODE_HAS_A_DETECTION_CONTROL,
    FAILURE_MODE_IS_BOUND,
    FAILURE_MODE_REACHES_A_HAZARD,
    PRIORITY_DOES_NOT_OVERRIDE_A_CONSTRAINT,
    SECURITY_JUDGEMENT_RESTS_ON_A_CURRENT_SNAPSHOT,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult
from src.domain.assurance.classification import TLP_ORDER, normalize_tlp
from src.domain.assurance.constraint_dispositions import ACCEPTED
from src.domain.assurance.failure_modes import NOT_CREDIBLE
from src.domain.assurance.fmea_action_priority import HIGH
from src.domain.assurance.fmea_factors import OCCURRENCE, SEVERITY, SEVERITY_SCALE
from src.domain.ontology_representation.attribute_scales import ordinal_rank

FAILURE_MODE = "failure-mode"
OUT_OF_SCOPE = "out-of-scope"
SAFETY_CLASSES = frozenset({"safety", "security"})


def check_failure_mode_is_bound(
    node: dict[str, object],
    bound_node_ids: frozenset[str],
    result: AssuranceVerificationResult,
) -> None:
    """A failure mode has to be a failure *of* something."""
    node_id = str(node["node_id"])
    if node_id in bound_node_ids or str(node.get("binding_status") or "") == OUT_OF_SCOPE:
        return
    result.issues.append(AssuranceIssue.of(
        FAILURE_MODE_IS_BOUND,
        message=(
            "Failure mode names no architecture element: add a 'binds-to' architecture reference "
            f"to the element that fails, or set binding_status to '{OUT_OF_SCOPE}' if it is "
            "outside this analysis."
        ),
        node_id=node_id,
    ))


def is_dismissed(node: dict[str, object]) -> bool:
    """Whether this cell was examined and judged not credible.

    The coverage rules below skip a dismissal, and must: a dismissed cell has no hazard and no
    detecting control *because that is what dismissing means*. Reporting both absences turns the
    cheaper of the two answers into the one that costs two permanent warnings, and an analyst who
    cannot make a finding go away by answering it honestly writes filler instead.
    """
    return str(attributes_of(node).get("assessment_state") or "") == NOT_CREDIBLE


def check_reaches_a_hazard(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    node_id = str(node["node_id"])
    if is_dismissed(node) or edges_from(edges, node_id, "leads-to"):
        return
    result.issues.append(AssuranceIssue.of(
        FAILURE_MODE_REACHES_A_HAZARD,
        message=(
            "Failure mode links to no hazard, so its severity cannot be derived and its row stays "
            "indeterminate. Add a 'leads-to' connection to the hazard this failure produces."
        ),
        node_id=node_id,
    ))


def check_has_a_detection_control(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    node_id = str(node["node_id"])
    if is_dismissed(node) or edges_into(edges, node_id, "detects"):
        return
    result.issues.append(AssuranceIssue.of(
        FAILURE_MODE_HAS_A_DETECTION_CONTROL,
        message=(
            "Nothing detects this failure mode, so its detectability is at its worst. That is "
            "usually a real verification gap rather than a modelling one."
        ),
        node_id=node_id,
    ))


def check_factor_assertions(
    node: dict[str, object],
    assessments: Sequence[Mapping[str, object]],
    derived_severity: str | None,
    current_digests: Mapping[str, str],
    result: AssuranceVerificationResult,
) -> None:
    """Every rule that reads a stored factor judgement, over one pass of its revisions."""
    node_id = str(node["node_id"])
    for assessment in assessments:
        factor = str(assessment.get("factor") or "")
        if not str(assessment.get("justification") or "").strip() or not str(
            assessment.get("author") or ""
        ).strip():
            result.issues.append(AssuranceIssue.of(
                ASSERTED_FACTOR_IS_ATTRIBUTABLE,
                message=(
                    f"Asserted {factor} carries no rationale or no author. A factor sets a "
                    "priority band, so it has to be readable and attributable without asking."
                ),
                node_id=node_id,
            ))
        if factor == SEVERITY and derived_severity is not None:
            asserted_rank = ordinal_rank(str(assessment.get("value") or ""), SEVERITY_SCALE)
            derived_rank = ordinal_rank(derived_severity, SEVERITY_SCALE)
            if asserted_rank is not None and derived_rank is not None and asserted_rank > derived_rank:
                result.issues.append(AssuranceIssue.of(
                    ASSERTED_SEVERITY_STAYS_WITHIN_THE_LOSSES,
                    message=(
                        f"Asserted severity '{assessment.get('value')}' exceeds the worst loss this "
                        f"failure mode reaches ('{derived_severity}'). Lowering a derived severity "
                        "with a rationale is legitimate; raising it invents consequence the hazard "
                        "chain does not contain."
                    ),
                    node_id=node_id,
                ))
    _check_applicability(node_id, assessments, current_digests, result)


def _check_applicability(
    node_id: str,
    assessments: Sequence[Mapping[str, object]],
    current_digests: Mapping[str, str],
    result: AssuranceVerificationResult,
) -> None:
    for factor, digest in sorted(current_digests.items()):
        for_factor = [a for a in assessments if str(a.get("factor") or "") == factor]
        if not for_factor or any(str(a.get("basis_digest") or "") == digest for a in for_factor):
            continue
        kind = (
            SECURITY_JUDGEMENT_RESTS_ON_A_CURRENT_SNAPSHOT
            if factor == OCCURRENCE
            else FACTOR_JUDGEMENT_STILL_APPLIES
        )
        result.issues.append(AssuranceIssue.of(
            kind,
            message=(
                f"The {factor} judgement was made against a picture of the model that has since "
                "changed, so it no longer applies and the derived value stands again. The "
                "judgement is retained — re-make it against the current basis if it still holds."
            ),
            node_id=node_id,
        ))


def check_priority_does_not_override_a_constraint(
    constraint: dict[str, object],
    edges: list[dict[str, object]],
    high_priority_failure_modes: frozenset[str],
    result: AssuranceVerificationResult,
) -> None:
    """A constraint carried as accepted while a failure mode it answers is high priority."""
    node_id = str(constraint["node_id"])
    if str(constraint.get("concern_class") or "") not in SAFETY_CLASSES:
        return
    if str(constraint.get("disposition") or "") != ACCEPTED.slug:
        return
    answered = {
        str(edge["target_id"]) for edge in edges_from(edges, node_id, "detects")
    } | {
        str(edge["source_id"]) for edge in edges_into(edges, node_id, "derives")
    }
    implicated = sorted(answered & high_priority_failure_modes)
    if not implicated:
        return
    result.issues.append(AssuranceIssue.of(
        PRIORITY_DOES_NOT_OVERRIDE_A_CONSTRAINT,
        message=(
            f"This constraint is carried as accepted while {len(implicated)} failure mode(s) it "
            f"answers are high priority: {', '.join(implicated)}. A priority band may never close, "
            "weaken or defer a safety or security constraint — decide the constraint on its own "
            "terms."
        ),
        node_id=node_id,
    ))


def check_analysed_element_has_failure_modes(
    arch_artifact_id: str,
    control_structure_node_ids: Sequence[str],
    result: AssuranceVerificationResult,
) -> None:
    """An element the control structure already names, never examined for failure modes."""
    result.issues.append(AssuranceIssue.of(
        ANALYSED_ELEMENT_HAS_FAILURE_MODES,
        message=(
            f"{arch_artifact_id} appears in the control structure "
            f"({', '.join(sorted(control_structure_node_ids))}) but has no failure modes. The "
            "hazard analysis already says this element matters; examining it costs a row per "
            "guideword, and a cell judged not credible counts as examined."
        ),
        node_id=sorted(control_structure_node_ids)[0] if control_structure_node_ids else "",
    ))


def check_evidence_is_not_less_restricted(
    evidence: dict[str, object],
    edges: list[dict[str, object]],
    nodes_by_id: Mapping[str, dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """Evidence must not be readable by someone who cannot read what it evidences.

    The exposure policy filters per node, so nothing else prevents a `TLP:WHITE` evidence node
    attached to a `TLP:GREEN` constraint — and its description would disclose the constraint to a
    reader who was never cleared to see it.
    """
    node_id = str(evidence["node_id"])
    evidence_tlp = normalize_tlp(str(evidence.get("tlp") or ""))
    evidenced = [
        nodes_by_id[str(edge["source_id"])]
        for edge in edges_into(edges, node_id, "evidenced-by")
        if str(edge["source_id"]) in nodes_by_id
    ]
    for subject in evidenced:
        subject_tlp = normalize_tlp(str(subject.get("tlp") or ""))
        if TLP_ORDER.index(evidence_tlp) >= TLP_ORDER.index(subject_tlp):
            continue
        result.issues.append(AssuranceIssue.of(
            EVIDENCE_IS_NOT_LESS_RESTRICTED,
            message=(
                f"Evidence is classified {evidence_tlp} while {subject['node_id']}, which it "
                f"evidences, is {subject_tlp}. A reader cleared only for the evidence would learn "
                "what the constraint says from it."
            ),
            node_id=node_id,
        ))


def high_priority_ids(priorities: Mapping[str, str]) -> frozenset[str]:
    return frozenset(node_id for node_id, band in priorities.items() if band == HIGH)
