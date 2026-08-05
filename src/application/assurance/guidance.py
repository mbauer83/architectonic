"""Per-step assurance method guidance content.

Failure-mode topics live in a sibling module and are merged in below — split only to keep both
modules inside the length policy, and looked up through the same function.

**Guidance never restates a vocabulary that code defines.** The UCA guidewords are composed here from
`domain.assurance.uca_guidewords`, because this module was the last place still carrying its own copy:
it taught the Handbook's four while the ontology, the matrix, the wizard and the attribute enum had all
moved to five. An analyst following the older text under-enumerates, and nothing failed to say so.
`tests/assurance/test_guidance_matches_vocabularies.py` holds the two together.
"""

from __future__ import annotations

from src.application.assurance.guidance_failure_modes import FAILURE_MODE_GUIDANCE
from src.domain.assurance.uca_guidewords import UCA_GUIDEWORDS

#: How this decomposition's step numbers relate to the Handbook's four, stated on every STPA topic
#: rather than in one of them: an analyst enters at whichever step they are on, and a numbering that
#: silently disagrees with the source reads as a miscount.
STPA_STEP_NUMBERING = (
    "This decomposition numbers six steps where the STPA Handbook has four. Losses (1) and hazards "
    "(2) are both the Handbook's Step 1; the control structure (3) is its Step 2; UCAs (4) are its "
    "Step 3; loss scenarios (5) are its Step 4. Constraints (6) are the one step the Handbook does "
    "not number on its own — it derives them inside the steps that produce them (system-level "
    "constraints with the hazards, controller constraints from the UCAs and scenarios). They are "
    "separated here so every constraint has a recorded derivation and its own completeness check. "
    "Nothing is added or omitted; the steps are split, not extended."
)

#: Topics the numbering statement applies to. CAST reuses the same model and is listed because its
#: guidance names STPA steps by number too.
_STPA_NUMBERED_TOPICS = frozenset(
    {
        "stpa-losses",
        "stpa-hazards",
        "stpa-control-structure",
        "stpa-ucas",
        "stpa-constraints",
        "stpa-loss-scenarios",
        "cast-investigation",
    }
)


#: Prose reads "five guidewords", not "5 guidewords" — and the count still comes from the vocabulary.
_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _count_word(count: int) -> str:
    return _COUNT_WORDS[count] if count < len(_COUNT_WORDS) else str(count)


def _guideword_walkthrough() -> str:
    """The guidewords as an analyst is asked them, numbered, from the one definition of them."""
    return " ".join(
        f"({index}) {word.label}"
        + (" — continuous control actions only:" if word.continuous_only else ":")
        + f" {word.question}"
        for index, word in enumerate(UCA_GUIDEWORDS, start=1)
    )


def _guideword_names() -> str:
    return ", ".join(
        word.label.lower() + (" (continuous control actions only)" if word.continuous_only else "")
        for word in UCA_GUIDEWORDS
    )

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
            f"{_count_word(len(UCA_GUIDEWORDS)).capitalize()} guidewords are applied to each control "
            f"action: {_guideword_names()}. "
            "The Handbook's second guideword — 'providing it causes a hazard' — is split here into "
            "provided in unsafe context and provided incorrectly, because those are different "
            "failures with different remedies: the first is a well-formed command issued in a state "
            "where it should not be (answered by a guard on state), the second a command whose "
            "content or parameters are wrong in a state where issuing it is correct (answered by "
            "validating the command). Recorded in one column, which of the two an analysis found is "
            "lost — and so is the constraint it implies."
        ),
        "why": (
            "UCAs are the direct cause of hazards in STAMP. Applying every guideword to every "
            "control action is what makes the enumeration complete rather than opportunistic. An "
            "analysis that applies four guidewords to a "
            f"{_count_word(len(UCA_GUIDEWORDS))}-guideword vocabulary silently omits a class of "
            "unsafe control."
        ),
        "how": (
            "For each control action on each controller, take the guidewords in turn and record the "
            f"context (state variables) under which each produces a UCA. {_guideword_walkthrough()} "
            "A guideword that cannot credibly apply is still an answer — record why, so an "
            "unstarted analysis cannot be mistaken for a finished one. Each UCA references exactly "
            "one control-action."
        ),
        "standards": ["STPA Handbook §2.5", "UCA guideword guide"],
    },
    "stpa-loss-scenarios": {
        "step": "STPA Step 5 — Identify Loss Scenarios",
        "what": (
            "A loss-scenario describes the causal factors that produce unsafe control or unsafe "
            "execution — why a controller would issue a UCA, or how a correct control action still "
            "leads to a hazard. Both Handbook classes share the node type and are distinguished by "
            "`scenario_type`: 'unsafe-control' (type a) explains one or more UCAs, and "
            "'improper-execution' (type b) explains a hazard directly, where the command was right "
            "but was not executed, was executed improperly, or was lost on the way through "
            "actuators and the controlled process — so no UCA is involved."
        ),
        "why": (
            "Every earlier step audits its own register: hazards against losses, UCAs against "
            "control actions, constraints against UCAs. Scenarios are where the analysis stops "
            "checking what it already wrote down and starts asking why any of it would happen — "
            "flawed process models, missing or stale feedback, degraded actuators, coordination "
            "between controllers that nobody owns. Skipping this step leaves a register of "
            "correct-looking constraints and no account of the causes they are supposed to remove."
        ),
        "how": (
            "Work outward from the control loop, not from a list. For a type-a scenario, take one "
            "UCA and ask what state of the controller's process model, or what feedback path, "
            "would make issuing it look correct at the time — then link it with `explains` to that "
            "UCA (and `concerns` to the control-structure node whose loop it sits on). For a "
            "type-b scenario, take a hazard and ask how a correct control action fails to reach or "
            "act on the controlled process, then link `explains` to the hazard. Each scenario "
            "`derives` one or more assurance-constraints — a scenario with no constraint has found "
            "a cause nobody is required to remove. In CAST, scenarios carry mode=observed and "
            "describe what actually happened rather than what could."
        ),
        "standards": [
            "STPA Handbook §2.6 (loss scenarios, classes a and b)",
            "CAST Handbook (Leveson) — scenarios as observed causal sequences",
        ],
    },
    "stpa-constraints": {
        "step": "STPA Step 6 — Derive Safety/Security Constraints",
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
            "Work from each UCA and each loss scenario: a UCA's constraint is its negation (the "
            "controller must not issue X in context Y), a scenario's constraint removes or detects "
            "the cause the scenario found — which is why the two steps produce different "
            "constraints from the same hazard. Hazards, incidents and corrective actions derive "
            "constraints too. Set concern_class, disposition, level. "
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
    """Return guidance for *topic*, fuzzy-matching against available keys.

    An STPA topic carries the numbering statement, added here rather than written into each entry:
    it is one fact about the whole decomposition, and six copies of it would be six things to keep
    true — which is the failure this module already had with the guidewords.
    """
    normalized = topic.lower().strip().replace(" ", "-")
    for key, value in _GUIDANCE.items():
        if key == normalized or normalized in key or key in normalized:
            numbering = {"step_numbering": STPA_STEP_NUMBERING} if key in _STPA_NUMBERED_TOPICS else {}
            return {"topic": key, **value, **numbering}
    return {
        "topic": topic,
        "available_topics": list(_GUIDANCE.keys()),
        "message": f"No guidance found for '{topic}'. Try one of the available topics.",
    }
