---
title: "CAST Investigation: [Incident Name]"
doc_type: cast-investigation
status: draft
incident_date: "YYYY-MM-DD"
analysis_baseline_id: ""
---

# CAST Investigation: [Incident Name]

## Incident Description

_What happened? When, where, and what loss occurred? Use factual language — observed, not interpreted._

- **Date/time:** YYYY-MM-DD HH:MM UTC
- **Incident entity ID:** INC@…
- **Concern class:** [safety | security | operational]
- **Loss(es) that occurred:**

## Control Structure As-Existed

_Describe the control structure at the time of the incident. Which controllers were active?
Which control actions and feedback loops were in play? Reference the assurance entities._

- **Baseline sealed:** [baseline_id] at [timestamp]
- **Control-structure-nodes involved:** CSN@… (role: controller/controlled-process)
- **Control actions relevant to the incident:** CAC@…

## Observed Control Flaws

_Which UCAs actually occurred? For each, what was the control action and in what context?
Link each to a `unsafe-control-action` entity with `mode=observed`._

| UCA ID | Control Action | Type | Context |
|---|---|---|---|
| UCA@… | [action name] | [not-provided / provided / wrong-timing / stopped-too-soon] | [context variables] |

## Causal Scenarios

_What sequence of events and conditions led from the control flaw to the hazard and then the loss?
Link each to a `loss-scenario` entity with `mode=observed`._

| Scenario ID | UCA(s) Explained | Hazard Violated | Causal Pathway |
|---|---|---|---|
| LSC@… | UCA@… | HAZ@… | [description] |

## Corrective Actions

_What recommendations emerge from this investigation?
Each corrective-action entity should derive at least one assurance-constraint._

| CRA ID | Name | Priority | Owner |
|---|---|---|---|
| CRA@… | [name] | [high / medium / low] | [owner] |

## Derived Constraints

_What assurance-constraints were derived from corrective-actions?
These enter the GRC lifecycle — each needs an owner, a disposition, and eventually evidence._

| Constraint ID | Derived From | Concern Class | Disposition | Owner |
|---|---|---|---|---|
| ACN@… | CRA@… | [safety / security] | [controlled-with-evidence] | [owner] |

## References

- CAST Handbook (Leveson) — §5 CAST methodology
- ISO 26262 Part 8 §9 — Incident investigation
- Incident report / evidence files
