"""The assurance verifier's finding codes and what each one denotes — declared once.

Rules live in several modules, grouped by the concern they check. Their codes are declared
here instead, for two reasons: a code that denotes two rules cannot be cited, suppressed or
documented unambiguously, and a code list kept in a docstring drifts from the rules it
describes. Every rule takes its code from this catalogue, so allocating a code and using it
are the same act.

Severity is part of the allocation. A hard finding blocks sign-off; an informational one never
blocks a write, and the distinction belongs with the code rather than with each call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: `info` is for findings that state something true about coverage rather than something wrong.
#: Without it, a rule that reports work not yet done has to be a warning, and a verifier that always
#: warns teaches its readers to stop reading it — which costs more than the finding was worth.
SeverityLiteral = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class AssuranceFindingKind:
    """One verifier rule: its code, whether it blocks sign-off, and what it requires."""

    code: str
    severity: SeverityLiteral
    requires: str
    """What the model must satisfy, stated positively."""


STORE_LOCKED = AssuranceFindingKind(
    code="E500",
    severity="error",
    requires="the store is unlocked, so there is something to verify",
)
UCA_NAMES_ONE_CONTROL_ACTION = AssuranceFindingKind(
    code="E501",
    severity="error",
    requires="an unsafe control action names exactly one control action it concerns",
)
CONSTRAINT_HAS_RESPONSIBLE_CONTROLLER = AssuranceFindingKind(
    code="E502",
    severity="error",
    requires="a safety or security constraint has a controller responsible for enforcing it",
)
SAFETY_CONSTRAINT_NOT_MERELY_ACCEPTED = AssuranceFindingKind(
    code="E503",
    severity="error",
    requires="a safety or security constraint is answered by something stronger than acceptance",
)
EDGE_ENDPOINTS_RESOLVE = AssuranceFindingKind(
    code="E504",
    severity="error",
    requires=(
        "both endpoints of every edge exist — navigation surfaces omit a dangling edge silently, "
        "so the verifier is the only place it becomes visible"
    ),
)
INCIDENT_INVESTIGATES_SOMETHING = AssuranceFindingKind(
    code="E505",
    severity="error",
    requires="an incident names what it investigates",
)
ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER = AssuranceFindingKind(
    code="E506",
    severity="error",
    requires="an accepted risk over a safety hazard is also treated by at least one constraint",
)
CONSTRAINT_IS_ENFORCED_OR_JUSTIFIED = AssuranceFindingKind(
    code="E510",
    severity="error",
    requires=(
        "a safety or security constraint either refines a requirement whose realization is the "
        "control measure, or carries a justification for how it is enforced"
    ),
)
CONTROL_NODE_IS_BOUND = AssuranceFindingKind(
    code="W501",
    severity="warning",
    requires="a control-structure node is bound to the architecture entity it stands for",
)
CONSTRAINT_HAS_EVIDENCE = AssuranceFindingKind(
    code="W502",
    severity="warning",
    requires="a constraint is substantiated by an evidence node or an evidencing artifact",
)
HAZARD_REACHES_A_LOSS = AssuranceFindingKind(
    code="W503",
    severity="warning",
    requires="a hazard leads to a loss, completing the causal chain",
)
OBLIGATION_REACHES_A_CONSTRAINT = AssuranceFindingKind(
    code="W504",
    severity="warning",
    requires="an obligation is complied with by at least one constraint",
)
RISK_HAS_A_TREATMENT = AssuranceFindingKind(
    code="W505",
    severity="warning",
    requires="a risk records how it is being treated",
)

# ── Failure-mode analysis ─────────────────────────────────────────────────────

FAILURE_MODE_IS_BOUND = AssuranceFindingKind(
    code="E507",
    severity="error",
    requires=(
        "a failure mode names the architecture element it belongs to, unless it is explicitly "
        "out of scope — a failure of nothing in particular cannot be acted on"
    ),
)
ASSERTED_FACTOR_IS_ATTRIBUTABLE = AssuranceFindingKind(
    code="E508",
    severity="error",
    requires=(
        "an asserted factor carries a rationale and an author — it sets a priority band, so an "
        "unexplained value cannot be defended in review"
    ),
)
ASSERTED_SEVERITY_STAYS_WITHIN_THE_LOSSES = AssuranceFindingKind(
    code="E509",
    severity="error",
    requires=(
        "an asserted severity does not exceed the worst loss the failure mode reaches — an "
        "assertion may lower severity with a rationale, never invent headroom the chain lacks"
    ),
)
EVIDENCE_IS_NOT_LESS_RESTRICTED = AssuranceFindingKind(
    code="E511",
    severity="error",
    requires=(
        "evidence is classified at least as restrictively as the most restricted thing it "
        "evidences, so it cannot disclose what a reader was not cleared to see"
    ),
)
FAILURE_MODE_REACHES_A_HAZARD = AssuranceFindingKind(
    code="W506",
    severity="warning",
    requires="a failure mode links its effect to a hazard, without which severity cannot be derived",
)
FAILURE_MODE_HAS_A_DETECTION_CONTROL = AssuranceFindingKind(
    code="W507",
    severity="warning",
    requires=(
        "a failure mode has a control that detects it; without one its detectability is at its "
        "worst, which is usually a real verification gap rather than a modelling one"
    ),
)
FACTOR_JUDGEMENT_STILL_APPLIES = AssuranceFindingKind(
    code="W508",
    severity="warning",
    requires="a factor judgement was made against the model as it now stands",
)
PRIORITY_DOES_NOT_OVERRIDE_A_CONSTRAINT = AssuranceFindingKind(
    code="W509",
    severity="warning",
    requires=(
        "no safety or security constraint is carried as accepted while a failure mode it answers "
        "is high priority — a priority band may never close, weaken or defer a constraint"
    ),
)
ANALYSED_ELEMENT_HAS_FAILURE_MODES = AssuranceFindingKind(
    code="W510",
    severity="warning",
    requires=(
        "an element the control structure already names has been examined for failure modes, "
        "even if the examination found none credible"
    ),
)
LOAD_BEARING_ELEMENT_IS_ANALYSED = AssuranceFindingKind(
    code="W511",
    # Informational: an element nobody has analysed yet is a statement about how far the analysis has
    # got, not a defect in it. On the repository this software describes there are over a hundred, and
    # as warnings they would swamp every real finding on every run.
    severity="info",
    requires=(
        "an element the graph shows to be load-bearing appears in some analysis — structure "
        "naming a gap the hazard analysis has not reached"
    ),
)
SEVERE_FAILURE_TOUCHES_CLASSIFIED_DATA = AssuranceFindingKind(
    code="W512",
    severity="warning",
    requires=(
        "data reached by a severe failure carries a classification — the analysis naming an "
        "unclassified-data gap in the architecture"
    ),
)
SECURITY_JUDGEMENT_RESTS_ON_A_CURRENT_SNAPSHOT = AssuranceFindingKind(
    code="W513",
    severity="warning",
    requires="a security-concern occurrence judgement rests on the current security snapshot",
)
REDUNDANT_ELEMENTS_DO_NOT_SHARE_A_CAUSE = AssuranceFindingKind(
    code="W515",
    severity="warning",
    requires=(
        "elements standing as each other's alternative do not both rely on the same thing — "
        "redundancy that shares a cause is not redundancy"
    ),
)


#: Every allocated kind. Declared last so it can name them all — a kind missing from here is
#: invisible to every check that iterates the catalogue, which is how a code comes to denote two
#: rules without anyone noticing.
ASSURANCE_FINDING_KINDS: tuple[AssuranceFindingKind, ...] = (
    STORE_LOCKED,
    UCA_NAMES_ONE_CONTROL_ACTION,
    CONSTRAINT_HAS_RESPONSIBLE_CONTROLLER,
    SAFETY_CONSTRAINT_NOT_MERELY_ACCEPTED,
    EDGE_ENDPOINTS_RESOLVE,
    INCIDENT_INVESTIGATES_SOMETHING,
    ACCEPTED_RISK_IS_NOT_THE_WHOLE_ANSWER,
    CONSTRAINT_IS_ENFORCED_OR_JUSTIFIED,
    CONTROL_NODE_IS_BOUND,
    CONSTRAINT_HAS_EVIDENCE,
    HAZARD_REACHES_A_LOSS,
    OBLIGATION_REACHES_A_CONSTRAINT,
    RISK_HAS_A_TREATMENT,
    FAILURE_MODE_IS_BOUND,
    ASSERTED_FACTOR_IS_ATTRIBUTABLE,
    ASSERTED_SEVERITY_STAYS_WITHIN_THE_LOSSES,
    EVIDENCE_IS_NOT_LESS_RESTRICTED,
    FAILURE_MODE_REACHES_A_HAZARD,
    FAILURE_MODE_HAS_A_DETECTION_CONTROL,
    FACTOR_JUDGEMENT_STILL_APPLIES,
    PRIORITY_DOES_NOT_OVERRIDE_A_CONSTRAINT,
    ANALYSED_ELEMENT_HAS_FAILURE_MODES,
    LOAD_BEARING_ELEMENT_IS_ANALYSED,
    SEVERE_FAILURE_TOUCHES_CLASSIFIED_DATA,
    SECURITY_JUDGEMENT_RESTS_ON_A_CURRENT_SNAPSHOT,
    REDUNDANT_ELEMENTS_DO_NOT_SHARE_A_CAUSE,
)
