"""Verifier rules about assurance constraints: ownership, disposition, enforcement, evidence.

A constraint is where an analysis turns into an obligation on the system, so these rules ask
whether anything actually answers it: somebody accountable for enforcing it, a strategy
stronger than carrying the exposure, a stated means of enforcement, and evidence.
"""

from __future__ import annotations

from src.application.verification._assurance_rule_support import attributes_of, edges_from, edges_into
from src.application.verification.assurance_findings import (
    CONSTRAINT_HAS_EVIDENCE,
    CONSTRAINT_HAS_RESPONSIBLE_CONTROLLER,
    CONSTRAINT_IS_ENFORCED_OR_JUSTIFIED,
    SAFETY_CONSTRAINT_NOT_MERELY_ACCEPTED,
)
from src.application.verification.assurance_issues import AssuranceIssue, AssuranceVerificationResult
from src.domain.assurance.constraint_dispositions import (
    ACCEPTED,
    CONSTRAINT_DISPOSITION_SLUGS,
    answers_by_argument,
)

SAFETY_CLASSES = frozenset({"safety", "security"})

#: Everything short of carrying the exposure as it stands. Derived from the vocabulary so a
#: value added there is offered here without a second edit.
_DISPOSITIONS_OPEN_TO_SAFETY: tuple[str, ...] = tuple(
    slug for slug in CONSTRAINT_DISPOSITION_SLUGS if slug != ACCEPTED.slug
)


def check_has_responsible_controller(
    node: dict[str, object],
    edges: list[dict[str, object]],
    result: AssuranceVerificationResult,
) -> None:
    """A safety or security constraint needs a controller responsible for enforcing it.

    Responsibilities assigned to control-structure entities are what refine a system-level
    constraint into something a part of the system actually carries.
    """
    node_id = str(node["node_id"])
    concern_class = str(node.get("concern_class") or "")
    if concern_class not in SAFETY_CLASSES:
        return
    if edges_into(edges, node_id, "responsible-for"):
        return
    result.issues.append(AssuranceIssue.of(
        CONSTRAINT_HAS_RESPONSIBLE_CONTROLLER,
        message=(
            f"Safety/security assurance-constraint ({concern_class}) must have an incoming "
            "'responsible-for' connection from the controller responsible for enforcing it."
        ),
        node_id=node_id,
    ))


def check_not_merely_accepted(
    node: dict[str, object],
    result: AssuranceVerificationResult,
) -> None:
    """Accepting a safety or security constraint is how a safety obligation gets priced away."""
    node_id = str(node["node_id"])
    concern_class = str(node.get("concern_class") or "")
    if concern_class not in SAFETY_CLASSES:
        return
    if str(node.get("disposition") or "") != ACCEPTED.slug:
        return
    alternatives = ", ".join(f"'{slug}'" for slug in _DISPOSITIONS_OPEN_TO_SAFETY)
    result.issues.append(AssuranceIssue.of(
        SAFETY_CONSTRAINT_NOT_MERELY_ACCEPTED,
        message=(
            f"disposition='{ACCEPTED.slug}' is rejected for {concern_class} constraints. "
            f"Use one of {alternatives}. The safety-subordination safeguard prevents "
            "pricing away safety obligations via risk acceptance."
        ),
        node_id=node_id,
    ))


def check_is_enforced_or_justified(
    node: dict[str, object],
    requirement_refining_node_ids: frozenset[str],
    result: AssuranceVerificationResult,
) -> None:
    """A safety or security constraint must say what enforces it.

    Either it refines an architecture requirement — whose realization is then the control
    measure — or it carries prose justifying how enforcement is achieved. Failing both, the
    constraint exists with nothing enforcing it and nothing noticing.
    """
    node_id = str(node["node_id"])
    concern_class = str(node.get("concern_class") or "")
    if concern_class not in SAFETY_CLASSES:
        return
    if node_id in requirement_refining_node_ids:
        return
    if str(attributes_of(node).get("enforcement_justification") or "").strip():
        return
    result.issues.append(AssuranceIssue.of(
        CONSTRAINT_IS_ENFORCED_OR_JUSTIFIED,
        message=(
            f"Safety/security assurance-constraint ({concern_class}) states no means of "
            "enforcement: add a 'refines-requirement' architecture reference to the requirement "
            "whose realization is the control measure, or record an 'enforcement_justification'."
        ),
        node_id=node_id,
    ))


def check_has_evidence(
    node: dict[str, object],
    edges: list[dict[str, object]],
    evidenced_ref_node_ids: frozenset[str],
    result: AssuranceVerificationResult,
) -> None:
    """A constraint with no evidence supports no claim in a published assurance case.

    Unless the constraint's answer is an argument rather than a control. `alarp-justified` says
    residual exposure remains and is argued to be as low as reasonably practicable, so there is no
    control whose working could be evidenced, and asking for some is asking for the artefact the
    disposition declares absent — which trains a reader to skip this code.

    Both conditions, not the disposition alone: an argued disposition with no justification written
    is an empty label, and `check_is_enforced_or_justified` above is already objecting to exactly
    that emptiness. So a constraint escapes this rule only where the argument is present and readable.
    """
    node_id = str(node["node_id"])
    if edges_from(edges, node_id, "evidenced-by") or node_id in evidenced_ref_node_ids:
        return
    argued = answers_by_argument(str(node.get("disposition") or ""))
    if argued and str(attributes_of(node).get("enforcement_justification") or "").strip():
        return
    result.issues.append(AssuranceIssue.of(
        CONSTRAINT_HAS_EVIDENCE,
        message=(
            "Assurance constraint has no evidence: add an 'evidenced-by' connection to an "
            "evidence node, or an 'evidenced-by-artifact' architecture reference."
        ),
        node_id=node_id,
    ))
