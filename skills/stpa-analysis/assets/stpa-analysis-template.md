---
title: "[System Name] STPA Analysis"
status: draft
concern_class: safety
analysis_scope: "[Brief description of system boundary and analysis scope]"
---

## Purpose and Scope

[State the system under analysis, the analysis objective, and what is
explicitly out of scope. Reference the system mission and key stakeholders.]

## Losses

| ID | Name | Concern Class |
|----|------|---------------|
| L-1 | [Loss of ...] | safety |

## Hazards

| ID | Name | Leads To |
|----|------|----------|
| H-1 | [System state that leads to L-1] | L-1 |

## Control Structure

[Reference the control-structure diagram by entity link. List key controllers and
controlled processes. Note binding status for each node.]

| Node | Role | Binding Status | Architecture Entity |
|------|------|----------------|---------------------|
| [Name] | controller | unbound-pending | — |

## Unsafe Control Actions

| ID | Control Action | UCA Type | Context | Violates |
|----|----------------|----------|---------|---------|
| UCA-1 | [Action] | not-provided | [State/context] | H-1 |

## Loss Scenarios

| ID | Description | Explains |
|----|-------------|----------|
| LS-1 | [How UCA leads to hazard] | UCA-1 |

## Assurance Constraints

| ID | Constraint | Derived From | Concern Class | Disposition |
|----|-----------|--------------|---------------|-------------|
| ACN-1 | [The controller shall/shall not ...] | UCA-1 | safety | controlled-with-evidence |

## References

- STPA Handbook (Leveson & Thomas)
- [Standards applicable to this analysis, e.g., ISO 26262, ISO/SAE 21434]
