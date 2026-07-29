# STPA Method Reference

## STAMP Concepts

**STAMP** (System-Theoretic Accident Model and Processes) treats accidents as
control problems, not failure chains. Three core axioms:

1. Safety is a control problem — accidents occur when unsafe control actions
   violate system safety constraints.
2. The control structure represents the sociotechnical system — controllers,
   controlled processes, and the actions/feedback between them.
3. Constraints, not barriers — safety requirements constrain the behaviour of
   the control structure.

## The Four STPA Steps

| Step | Output | Key edge types |
|------|--------|----------------|
| 1. Identify Losses | `loss` nodes | — |
| 2. Identify Hazards | `hazard` nodes | `leads-to` (hazard→loss) |
| 3. Model Control Structure | `control-structure-node`, `control-action` | `issues`, `acts-on`, `feedback` |
| 4. UCAs → Constraints | `unsafe-control-action`, `loss-scenario`, `assurance-constraint` | `concerns`, `violates`, `explains`, `derives` |

## UCA Guidewords

| uca_type | Meaning |
|----------|---------|
| `not-provided` | Control action not given when needed |
| `provided-when-unsafe` | Control action given in an unsafe context |
| `wrong-timing` | Control action given too early or too late |
| `stopped-too-soon` | Stopped before completing / applied too long |

## Key Terms

**Loss** — An unacceptable outcome stakeholders must avoid.
**Hazard** — A system state that, with worst-case environment, leads to a loss.
**Control action** — A specific command from a controller to a controlled process.
**UCA** — A control action that is unsafe in a particular context.
**Loss scenario** — A causal explanation for how a UCA leads to a hazard.
**Assurance constraint** — A constraint on the control structure derived from a UCA.

## STPA-Sec Extension

STPA-Sec applies STPA to security: `concern_class="security"`, losses include
data breaches and integrity violations. UCA guidewords remain identical.
Reference: ISO/SAE 21434 Clause 9 (TARA) for the security parallel.

## Sources

- Leveson & Thomas, STPA Handbook — https://www.flighttestsafety.org/images/STPA_Handbook.pdf
- STAMP/STPA/CAST overview (UL) — https://www.ul.com/sis/blog/introduction-to-stamp-stpa-and-cast
- STPA-Sec — https://pmc.ncbi.nlm.nih.gov/articles/PMC7959614/
