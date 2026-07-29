"""Per-step failure-mode analysis guidance content.

Split from the STPA/CAST/GRC topics purely to keep both modules inside the length policy; they are
merged into one lookup.

The framing in these topics is deliberate and load-bearing. Failure-mode analysis is **not**
additional coverage on top of a control-structure analysis: it cannot find a control or coordination
flaw where nothing failed, which is most of what STPA exists for. What it buys is per-component
enumeration and defensible prioritisation of effort. Presenting it as extra coverage would invite
exactly the wrong conclusion — that a completed matrix means the system has been analysed.
"""

from __future__ import annotations

_STANDARDS = ["SAE J1739", "AIAG-VDA FMEA Handbook (2019)", "IEC 60812:2018"]

FAILURE_MODE_GUIDANCE: dict[str, dict[str, object]] = {
    "fmea-failure-modes": {
        "step": "Failure modes — enumerate how each component fails",
        "what": (
            "A failure mode is one way a single component or function fails to perform as "
            "intended. Each is enumerated against five guidewords: no function, partial or "
            "degraded function, excessive function, intermittent function, unintended function."
        ),
        "why": (
            "This is what a control-structure analysis deliberately does not give you: it asks "
            "how the system's control can produce a loss, not how each part fails. Neither "
            "covers the other's ground — a failure-mode analysis cannot find a coordination flaw "
            "where nothing failed, and a control-structure analysis will not tell you which "
            "component to harden next. Treat this as prioritisation of effort, never as extra "
            "coverage."
        ),
        "how": (
            "Work from the elements the control structure already names — those are the ones the "
            "hazard analysis says matter, and there are few enough to finish. For each, take the "
            "five guidewords in turn. A guideword that cannot credibly apply is recorded as not "
            "credible with a reason: that is an answer, it counts as coverage, and it is what "
            "stops an unstarted matrix looking like a finished one."
        ),
        "standards": _STANDARDS,
    },
    "fmea-effects": {
        "step": "Effects — link each failure to the hazard it produces",
        "what": (
            "A failure mode's effect is an existing hazard, linked with 'leads-to'. There is no "
            "separate effect or consequence concept to create."
        ),
        "why": (
            "The hazard analysis already holds the consequences and their severities. Writing the "
            "effect out again as its own node would start a second consequence vocabulary beside "
            "the first, and the two would drift. Linking instead is also what makes severity "
            "derivable rather than something to re-enter by hand."
        ),
        "how": (
            "Ask what system state this failure puts the system into, then find that hazard. If "
            "no hazard fits, the gap is in the hazard analysis, not here — add it there first. "
            "Until an effect is linked the row has no severity and stays undecided, which the "
            "matrix shows rather than hiding."
        ),
        "standards": _STANDARDS,
    },
    "fmea-causes": {
        "step": "Causes — record why the failure happens, where it is known",
        "what": (
            "A cause is a loss scenario that explains the failure mode. Optional: a failure mode "
            "with no scenario is still a valid row."
        ),
        "why": (
            "The causal story is the same concept a control-structure analysis already uses to "
            "explain unsafe control actions, so it is reused rather than restated. Its absence "
            "weakens the rationale behind an occurrence judgement without blocking anything."
        ),
        "how": (
            "Where the mechanism is understood, write it as a loss scenario and link it with "
            "'explains'. Where it is not, leave it — an invented cause is worse than an absent one."
        ),
        "standards": _STANDARDS,
    },
    "fmea-controls": {
        "step": "Controls — what prevents the failure, and what would reveal it",
        "what": (
            "Two different kinds, deliberately kept apart. A prevention control is a constraint "
            "the failure mode derives. A detection control is a constraint that 'detects' the "
            "failure mode — it reveals the failure before its effect propagates."
        ),
        "why": (
            "Detectability is a property of the detection controls that exist and of nothing "
            "else. Declared telemetry on the element is shown beside the row as context for "
            "whoever writes the next control, but it never raises the band: a component that "
            "emits logs is not thereby a component whose silent partial-output failure is noticed."
        ),
        "how": (
            "Write the prevention control as a constraint derived from the failure mode. Write "
            "the detection control as a constraint that detects it, and evidence it — an "
            "evidenced control counts for more than an asserted one, and one an automated gate "
            "exercises counts for most. A failure mode nothing detects sits at the worst "
            "detectability band, which is usually a real verification gap rather than a "
            "modelling one."
        ),
        "standards": _STANDARDS,
    },
    "fmea-factors": {
        "step": "Factors — severity, occurrence, detectability, and the priority they set",
        "what": (
            "Severity and detectability are derived from the model: severity from the worst loss "
            "the failure reaches along the hazard chain, detectability from the detection "
            "controls present. Occurrence is asserted by a person, with a rationale. Action "
            "Priority is a decision table over the three."
        ),
        "why": (
            "Occurrence is a claim about how often something happens, and nothing in the model "
            "measures a failure rate. Complexity correlates weakly with defect density, churn "
            "measures recent change, coverage measures testing — none is a frequency. A value "
            "derived from any of them would look computed and move real decisions. So the model "
            "contributes the evidence and a person contributes the judgement."
        ),
        "how": (
            "Link the effect and the controls first; severity and detectability then appear "
            "without being asked for. Occurrence is requested only where it could change the "
            "band — many rows complete with no numeric input at all. Every asserted value needs "
            "a rationale, and a judgement stops applying by itself when the model it was made "
            "against changes."
        ),
        "standards": _STANDARDS,
        "if_you_already_know_fmea": (
            "Two deliberate differences. There is no risk priority number: multiplying three "
            "ordinals treats them as ratio quantities, and equal products hide very different "
            "situations — a 10x1x1 and a 1x10x1 both score 10 while only one of them is "
            "catastrophic. A decision table replaces it, as the 2019 handbook did. And the "
            "detection axis is named detectability and runs the other way from conventional D "
            "numbers: higher means MORE detectable, so the worst case is the lowest band."
        ),
        "priority_never_overrides_a_constraint": (
            "An Action Priority may never close, weaken, defer or justify the disposition of a "
            "safety or security constraint. It ranks where to spend effort; it is not a verdict "
            "on an obligation, and there is no affordance anywhere that turns a low band into a "
            "dismissal. A constraint carried as merely accepted while a failure mode it answers "
            "is high priority is reported as a finding."
        ),
        "targeting_signals_are_not_factors": (
            "Signals such as how many typed dependents an element carries, whether it is a sole "
            "provider, or how sensitive the data it touches is, are shown beside the row to help "
            "decide where to look next. They are never composed into a score and never become a "
            "factor value: a composite would need weights nobody can defend."
        ),
    },
}
