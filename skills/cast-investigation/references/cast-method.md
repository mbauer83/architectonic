# CAST Method Reference

## What is CAST?

**CAST (Causal Analysis using System Theory)** is the reactive counterpart of STPA. Both are
based on STAMP (Systems-Theoretic Accident Model and Processes, Leveson 2004).

Where STPA asks "what could go wrong?", CAST asks "what *did* go wrong and why?"

CAST reuses ~90% of the STPA ontology and adds: `incident`/`accident`, `corrective-action`,
and an `observed` mode on UCAs and loss-scenarios.

## Core Concepts

### Incident / Accident
An actual occurred loss event under investigation. CAST distinguishes:
- **Accident**: an event involving a loss (injury, death, damage)
- **Incident**: a near-miss or event that reveals hazardous conditions

In the assurance model both are `incident` entities (discriminated by name/content).

### The Control Structure As-Existed
CAST reconstructs the control structure **as it existed at the time of the incident** —
not as it was designed or as it is now. This is why the `analysis_baseline` (§10) is required:
it pins the exact model state for reproducibility.

### Observed vs Hypothesized
- STPA UCAs: `mode=hypothesized` (could happen)
- CAST UCAs: `mode=observed` (did happen — found by investigating what actually occurred)

### Corrective Actions vs Constraints
- **Corrective-action**: a recommendation from the investigation
- **Assurance-constraint**: the derived system requirement (what the system must/must not do)
- The chain: `incident → corrective-action → derives → assurance-constraint`

## CAST vs STPA

| Aspect | STPA | CAST |
|---|---|---|
| When | Before the incident | After the incident |
| Mode | Hypothesized | Observed |
| Anchor | Analysis scope | Incident/accident entity |
| Starting point | System purpose → losses | Actual loss event |
| Output | Constraints to prevent hazards | Corrective constraints to prevent recurrence |
| Requires baseline | No | Yes (for reproducibility) |

## Standards References

- **STAMP/STPA Handbook** (Leveson & Thomas) §5 — CAST methodology
- **ISO 26262** Part 8 §9 — Safety element out-of-context (incident investigation)
- **ISO/SAE 21434** Clause 11 — Cybersecurity incident response
- **NIST SP 800-61** — Computer security incident handling guide (for security incidents)
- **EU AI Act Art. 62** — Post-market monitoring and incident reporting obligations
