---
title: "[System Name] Assurance Case"
status: draft
claim_type: safety
---

# [System Name] Assurance Case

## Purpose and Scope

**Purpose:** This document presents the structured safety/security argument for [system name],
demonstrating that the system satisfies its [safety/security/combined] claims within the
defined operational context.

**Scope:** [Describe the system boundary, operational context, and any assumptions about
the environment. Reference the STPA analysis scope and concern classes covered.]

**Claim type:** [safety | security | combined]

**Related analyses:**
- STPA Analysis: [document reference]
- CAST Investigations (if applicable): [document references]
- GRC Risk Assessment (if applicable): [document reference]

---

## Safety/Security Claims

List the top-level claims this assurance case argues:

| # | Claim | GSN Node | Status |
|---|-------|----------|--------|
| 1 | The system prevents [Loss L1] | G-TOP | argued |
| 2 | Hazard [H1] is controlled | G-H1 | argued |
| … | … | … | … |

**Losses addressed:** [List all loss entities from the STPA analysis]

**Hazards addressed:** [List all hazard entities with their concern class]

---

## GSN Argument Structure

[Reference or embed the GSN diagram artifact here]

**Diagram:** [gsn diagram artifact ID or link]

### Top Goal

**G-TOP:** [State the overall safety/security claim derived from losses]

*Supported by:* S-OVERALL (Argument by STPA hazard decomposition)

*In context of:* C-SCOPE ([Scope assumption])

### Strategy

**S-OVERALL:** Argument by constraint derivation from STPA hazard analysis.

*Sub-goals:* [List G-H1, G-H2, … one per hazard]

### Hazard Sub-Goals

For each hazard:

**G-H[n]:** "[Hazard name] is controlled."

*Supported by:* S-H[n] (Argument by constraint derivation from UCAs)

*Sub-goals:*
- G-C[m]: "Constraint [name] holds" — supported by Sn-[evidence ref]

---

## Evidence Summary

| Constraint | Evidence Artefact | Type | Status |
|------------|------------------|------|--------|
| [ACN-001]  | [Test report ref] | Test | accepted |
| …          | …                | …    | … |

**Note:** All `evidenced-by` edges must be present in the assurance store
before argument completeness can be confirmed. Run `assurance_case_completeness`
to verify.

---

## Argument Completeness

**Completeness check result:** [passed | failed — [n] gap(s)]

| Check | Result | Gap Count |
|-------|--------|-----------|
| constraint_has_evidence | [pass/fail] | [n] |
| hazard_has_constraint | [pass/fail] | [n] |
| loss_has_hazard | [pass/fail] | [n] |

**Outstanding gaps:** [List any open sub-goals with resolution plan and target date]

**Completeness confirmed by:** [Name, role] on [date]

---

## Sign-off

This assurance case was reviewed and accepted by:

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Safety/Security Lead | | | |
| System Architect | | | |
| [Certifying Authority] | | | |

**Status at sign-off:** complete

---

## References

- [STPA Analysis document]
- [GSN diagram artifact]
- [Evidence artefacts — list each with ID and location]
- [Applicable standards: GSN Community Standard v3, DO-178C, IEC 62443-4-1, etc.]
