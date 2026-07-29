# Script: Argument Completeness Check

## Overview

`assurance_case_completeness` verifies that the assurance argument chain is
fully supported by evidence. It must pass before sign-off on an assurance-case document.

---

## Calling the Tool

```
assurance_case_completeness()
```

No parameters required. The store must be unlocked.

---

## Understanding the Three Checks

### Check 1: `constraint_has_evidence`

Every `assurance-constraint` entity in the store must have at least one
outgoing `evidenced-by` edge pointing to an evidence artefact.

**Fails when:** A constraint exists but has no evidence linked.

**Resolution:**
1. Identify which evidence artefacts support the constraint
2. Create the evidence artefact node if it does not exist:
   ```
   assurance_create_node(node_type="evidence", name="Test Report T-001", ...)
   ```
3. Link constraint to evidence:
   ```
   assurance_add_edge(source_id=constraint_id, target_id=evidence_id, conn_type="evidenced-by")
   ```

### Check 2: `hazard_has_constraint`

Every `hazard` entity must have at least one `assurance-constraint` derived
via the UCA chain: hazard ← (violates) ← UCA → (derives) → constraint.

Also accepts: hazard ← UCA ← (explains) ← loss-scenario → (derives) → constraint.

**Fails when:** A hazard exists but no UCA violates it and derives a constraint.

**Resolution:**
1. Identify which UCAs should violate this hazard
2. If UCAs exist but lacks `derives` edge:
   ```
   assurance_add_edge(source_id=uca_id, target_id=constraint_id, conn_type="derives")
   ```
3. If no UCAs exist for this hazard — complete UCA analysis:
   ```
   assurance_create_node(node_type="unsafe-control-action", name="...", uca_type="not-provided")
   assurance_add_edge(source_id=uca_id, target_id=hazard_id, conn_type="violates")
   assurance_add_edge(source_id=uca_id, target_id=control_action_id, conn_type="concerns")
   ```

### Check 3: `loss_has_hazard`

Every `loss` entity must have at least one `hazard` with a `leads-to` edge
pointing to it.

**Fails when:** A loss exists but no hazard leads to it.

**Resolution:**
```
assurance_add_edge(source_id=hazard_id, target_id=loss_id, conn_type="leads-to")
```

---

## Interpreting the Result

```json
{
  "passed": false,
  "summary": "3 completeness gap(s) found across 2 check(s).",
  "checks": {
    "constraint_has_evidence": {
      "passed": false,
      "gap_count": 2,
      "gaps": [
        {"node_id": "ACN@001", "name": "Speed limit enforcement"},
        {"node_id": "ACN@002", "name": "Brake force constraint"}
      ]
    },
    "hazard_has_constraint": {
      "passed": true,
      "gap_count": 0,
      "gaps": []
    },
    "loss_has_hazard": {
      "passed": false,
      "gap_count": 1,
      "gaps": [
        {"node_id": "LOSS@003", "name": "Mission failure"}
      ]
    }
  }
}
```

Work through each failing check in order: `loss_has_hazard` → `hazard_has_constraint` → `constraint_has_evidence`.
This ordering ensures the chain is complete before adding evidence.

---

## Relationship to Other Checks

| Tool | What it checks | When to run |
|------|---------------|-------------|
| `assurance_verify` | Hard structural rules (§17A) | Always — blocks invalid data |
| `assurance_stpa_complete` | Full STPA chain (§17B) | After STPA Steps 1–5 |
| `assurance_grc_complete` | GRC obligations and risks | After GRC analysis |
| `assurance_case_completeness` | Argument completeness for sign-off | Before assurance-case sign-off |
| `assurance_coverage` | Dashboard of all gaps | At any time for overview |

Run in this order for a complete pre-sign-off check:
1. `assurance_verify` — fix any errors before proceeding
2. `assurance_stpa_complete` — confirm STPA analysis is complete
3. `assurance_case_completeness` — confirm evidence coverage is complete
4. Update assurance-case document "Argument Completeness" section
5. Set document status to "complete" and submit for sign-off

---

## Document Update After Passing

After all checks pass, update the assurance-case document:

```markdown
## Argument Completeness

**Completeness check result:** passed

| Check | Result | Gap Count |
|-------|--------|-----------|
| constraint_has_evidence | pass | 0 |
| hazard_has_constraint | pass | 0 |
| loss_has_hazard | pass | 0 |

**Completeness confirmed by:** [Name] on [Date]
```

Then update `status: complete` in the document frontmatter.
