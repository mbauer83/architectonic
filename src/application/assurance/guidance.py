"""Per-step assurance method guidance content.

Failure-mode topics live in a sibling module and are merged in below — split only to keep both
modules inside the length policy, and looked up through the same function.
"""

from __future__ import annotations

from src.application.assurance.guidance_failure_modes import FAILURE_MODE_GUIDANCE

_GUIDANCE: dict[str, dict[str, object]] = {
    "stpa-losses": {
        "step": "STPA Step 1 — Identify Losses",
        "what": (
            "A loss is an unacceptable outcome stakeholders must avoid: loss of life, injury, "
            "property damage, mission failure, privacy violation, regulatory non-compliance."
        ),
        "why": (
            "Losses anchor the entire analysis. Every hazard, UCA, and constraint traces back "
            "to one or more losses. Without losses, STPA has no direction."
        ),
        "how": (
            "Brainstorm stakeholder-relevant outcomes to avoid. Use broad categories first "
            "(safety, security, financial, privacy). Each loss should be a noun phrase, "
            "e.g. 'Loss of vehicle control', 'Breach of personal data'."
        ),
        "standards": [
            "STPA Handbook (Leveson & Thomas) §2.2",
            "ISO 26262 Part 3 §6 (hazard analysis and risk assessment)",
        ],
    },
    "stpa-hazards": {
        "step": "STPA Step 2 — Identify System-Level Hazards",
        "what": (
            "A hazard is a system state that, with worst-case environment, leads to a loss. "
            "It describes the system state, not the cause or outcome."
        ),
        "why": (
            "Hazards bridge losses and the control structure. They are system-level "
            "(not component-level) to remain stable across design changes."
        ),
        "how": (
            "For each loss, ask: what system state could produce this loss? "
            "Write hazards as system states, e.g. 'Vehicle moves at unsafe speed for road conditions'."
        ),
        "standards": ["STPA Handbook §2.3", "ISO/SAE 21434 Clause 9 (TARA)"],
    },
    "stpa-control-structure": {
        "step": "STPA Step 3 — Model the Control Structure",
        "what": (
            "The control structure is a hierarchical diagram of controllers and controlled "
            "processes connected by control actions and feedback — the STAMP governance model."
        ),
        "why": (
            "UCAs can only be identified with respect to a specific control action on a specific "
            "control loop. The control structure makes those loops explicit."
        ),
        "how": (
            "Identify controllers (issue commands), controlled processes (receive commands), "
            "control actions (specific commands), and feedback signals. Mark binding_status for each node."
        ),
        "standards": ["STPA Handbook §2.4", "STAMP/STPA overview (UL)"],
    },
    "stpa-ucas": {
        "step": "STPA Step 4 — Identify Unsafe Control Actions (UCAs)",
        "what": (
            "A UCA is a specific control action unsafe in a particular context. "
            "Four types: (1) not provided, (2) provided when unsafe, "
            "(3) wrong timing, (4) stopped too soon / applied too long."
        ),
        "why": (
            "UCAs are the direct cause of hazards in STAMP. Systematically applying "
            "the four guidewords to each control action ensures completeness."
        ),
        "how": (
            "For each control action on each controller, apply all four guidewords. Record the "
            "context (state variables) under which each guideword produces a UCA. "
            "Each UCA must reference exactly one control-action."
        ),
        "standards": ["STPA Handbook §2.5", "UCA guideword guide"],
    },
    "stpa-constraints": {
        "step": "STPA Step 5 — Derive Safety/Security Constraints",
        "what": (
            "An assurance-constraint is a requirement derived from UCAs: "
            "'The controller must/must not issue action X in context Y.' "
            "Constraints are the actionable output of STPA."
        ),
        "why": (
            "Constraints are directly implementable and testable. They link hazard analysis "
            "to system requirements (via the refines-requirement architecture reference) and "
            "to evidence (via evidenced-by)."
        ),
        "how": (
            "For each UCA, derive its negation as a constraint. Set concern_class, disposition, level. "
            "Link to an ArchiMate requirement via a refines-requirement architecture reference. "
            "Assign the responsible controller via an incoming responsible-for connection."
        ),
        "standards": ["STPA Handbook §2.6", "ISO 26262 Part 4 §6 (functional safety concept)"],
    },
    "grc-risk": {
        "step": "GRC — Risk Evaluation",
        "what": (
            "A risk entity evaluates a hazard or loss-scenario: likelihood × impact = risk score. "
            "OPTIONAL — constraints are valid without a risk entity, and a risk evaluation can "
            "never be a precondition for one existing."
        ),
        "why": (
            "Risk prioritises which constraints to treat first, but never closes a safety/security "
            "constraint. treatment=accept cannot be the sole disposition of a safety hazard."
        ),
        "how": (
            "Create a risk entity, set likelihood and impact, connect via assesses→hazard "
            "and treated-by→assurance-constraint. Assign an owner. Set review_date."
        ),
        "standards": ["ISO 31000:2018 §6 (risk treatment)", "Cerrix risk register best practices"],
    },
    "grc-obligations": {
        "step": "GRC — Compliance Obligations",
        "what": (
            "An obligation entity represents a compliance instance: 'Does our system comply "
            "with clause X of standard Y?' Status and evidence are assurance-owned and confidential."
        ),
        "why": (
            "Obligations close the loop between technical constraints and regulatory requirements. "
            "They enable an auditable compliance statement."
        ),
        "how": (
            "Create an obligation, set the cites attribute to a scheme:code reference (e.g. ISO26262:6-8). "
            "Link assurance-constraints via complies-with. Add evidenced-by connections for evidence."
        ),
        "standards": [
            "ISO 27001:2022 Annex A controls",
            "GDPR Art. 5 (data processing principles)",
            "EU AI Act Art. 12/18/19/26",
        ],
    },
    "assurance-case-gsn": {
        "step": "Assurance Case — Build GSN Argument",
        "what": (
            "A GSN (Goal Structuring Notation) assurance case is a structured argument that the system "
            "meets its safety/security claims. Notation: G=Goal (claim to be argued), S=Strategy "
            "(how the argument proceeds), Sn=Solution (evidence node), C=Context (scope/assumption), "
            "A=Assumption, J=Justification. Connections: 'supported-by' decomposes goals downward; "
            "'in-context-of' links contextual information."
        ),
        "why": (
            "GSN externalises the argument so it can be reviewed and challenged. Regulators (DO-178C, "
            "IEC 62443, EU AI Act) and certification bodies often require an explicit safety/security "
            "argument, not just evidence in isolation."
        ),
        "how": (
            "1. Use assurance_draft_gsn to scaffold the initial argument from your STPA analysis. "
            "2. Review the returned top_goal, sub_goals, strategies, solutions, and gaps. "
            "3. Create a gsn diagram artifact with the scaffolded nodes and edges. "
            "4. Fill gaps: add evidenced-by edges to constraints and add UCAs for unconstrained hazards. "
            "5. Produce an assurance-case document using the assurance-case doc type."
        ),
        "standards": [
            "GSN Community Standard v3 (Goal Structuring Notation)",
            "SACM (OMG Structured Assurance Case Metamodel) v2.2",
            "DO-178C §12 (software life cycle data), ARP4761 §A.4 (safety assessment)",
            "IEC 62443-4-1 §SR 2.13 (security case)",
        ],
    },
    "assurance-case-completeness": {
        "step": "Assurance Case — Argument Completeness",
        "what": (
            "Argument completeness means every claim in the assurance case is supported by evidence "
            "all the way down the argument tree. Three key checks: (1) every assurance-constraint has "
            "≥1 evidenced-by edge pointing to evidence; (2) every hazard has ≥1 constraint derived "
            "from a UCA (via the UCA derives chain); (3) every loss has ≥1 hazard leading to it."
        ),
        "why": (
            "An incomplete argument has open sub-goals — claims without evidence or claims without "
            "sub-goals. Open sub-goals are certification blockers. Completeness must be demonstrated "
            "before sign-off."
        ),
        "how": (
            "1. Run assurance_case_completeness to identify all gaps. "
            "2. For each constraint without evidence: create evidence artifacts (test reports, audit "
            "records, formal proofs) and add evidenced-by edges. "
            "3. For each hazard without constraints: complete the STPA UCA analysis and derive constraints. "
            "4. For each loss without hazards: add hazards with leads-to edges. "
            "5. Re-run until all checks pass, then document in the 'Argument Completeness' section."
        ),
        "standards": [
            "GSN Community Standard v3 §5 (completeness and consistency)",
            "DO-178C §12.3.5 (evidence traceability)",
            "STPA Handbook §2.6 (constraint derivation)",
        ],
    },
    "cast-investigation": {
        "step": "CAST — Incident/Accident Investigation",
        "what": (
            "CAST (Causal Analysis using System Theory) is the reactive counterpart of STPA. "
            "It reconstructs the control structure as-existed at the incident and derives corrective constraints."
        ),
        "why": (
            "CAST reuses the STAMP model and adds incident entity, observed UCAs (mode=observed), "
            "and corrective-actions. Corrective constraints enter the same GRC lifecycle as STPA constraints."
        ),
        "how": (
            "Create an incident entity, seal an analysis_baseline to pin the model state, "
            "then trace observed UCAs and loss-scenarios back to the incident. "
            "Derive corrective-action entities and then constraints."
        ),
        "standards": ["CAST Handbook (Leveson)", "STPA/CAST overview (UL)"],
    },
}


_GUIDANCE.update(FAILURE_MODE_GUIDANCE)


def lookup(topic: str) -> dict[str, object]:
    """Return guidance for *topic*, fuzzy-matching against available keys."""
    normalized = topic.lower().strip().replace(" ", "-")
    for key, value in _GUIDANCE.items():
        if key == normalized or normalized in key or key in normalized:
            return {"topic": key, **value}
    return {
        "topic": topic,
        "available_topics": list(_GUIDANCE.keys()),
        "message": f"No guidance found for '{topic}'. Try one of the available topics.",
    }
