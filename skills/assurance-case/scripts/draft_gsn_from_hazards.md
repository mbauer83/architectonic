# Script: Draft GSN from Hazards

## Overview

`assurance_draft_gsn` reads the confidential assurance store and scaffolds a
GSN argument structure from existing STPA content (losses, hazards, UCAs,
constraints, evidence).

Call this after completing at least Steps 1–5 of the STPA analysis.

---

## Calling the Tool

```
assurance_draft_gsn()
```

No parameters required. The store must be unlocked.

---

## Interpreting the Result

The tool returns a dict with five keys:

### `top_goal`

```json
{
  "node_id": "G-TOP",
  "gsn_type": "goal",
  "claim": "The system prevents: Loss of vehicle control, Data breach",
  "source_losses": ["LOSS@001", "LOSS@002"]
}
```

This is the top-level G node of your GSN diagram. The claim text is auto-generated
from all loss entity names. Refine the wording before including it in the diagram.

### `sub_goals`

One entry per hazard in the store:

```json
[
  {
    "node_id": "G-HAZ@001",
    "gsn_type": "goal",
    "claim": "Hazard 'Vehicle at unsafe speed' is controlled",
    "source_hazard": "HAZ@001",
    "leads_to_losses": ["LOSS@001"]
  }
]
```

Each sub_goal should become a child G node under the top_goal via `supported-by`.

### `strategies`

One entry per hazard, linking UCAs and constraints:

```json
[
  {
    "node_id": "S-HAZ@001",
    "gsn_type": "strategy",
    "description": "Argument by constraint derivation from STPA UCAs",
    "source_hazard": "HAZ@001",
    "uca_ids": ["UCA@001", "UCA@002"],
    "constraint_ids": ["ACN@001"]
  }
]
```

This maps to the S node under each sub_goal.

### `solutions`

One entry per evidenced constraint:

```json
[
  {
    "node_id": "Sn-EVID@001",
    "gsn_type": "solution",
    "description": "Evidence for constraint 'Speed limit enforcement'",
    "constraint_id": "ACN@001",
    "evidence_id": "EVID@001"
  }
]
```

These become Sn (solution) leaf nodes in the GSN tree.

### `gaps`

```json
{
  "constraints_without_evidence": [
    {"node_id": "ACN@002", "name": "Brake-force constraint"}
  ],
  "hazards_without_constraints": [
    {"node_id": "HAZ@003", "name": "Sensor failure state"}
  ]
}
```

**These gaps represent open sub-goals** — certification blockers that must be
resolved before argument completeness can be confirmed.

---

## Next Steps After Drafting

1. Review all `sub_goals` — refine claim text for clarity
2. Close `gaps.constraints_without_evidence`:
   - Add evidence artefacts via `assurance_create_node` + `assurance_add_edge` (evidenced-by)
3. Close `gaps.hazards_without_constraints`:
   - Complete UCA analysis for the hazard (see stpa-analysis skill)
   - Derive constraints via `derives` edges
4. Re-run `assurance_draft_gsn` to confirm all gaps are closed
5. Create the `gsn` diagram artifact from the scaffolded content
6. Produce the `assurance-case` document

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `top_goal.claim` is generic | No losses in store | Add losses first (STPA Step 1) |
| `sub_goals` is empty | No hazards in store | Add hazards (STPA Step 2) |
| All constraints in gaps | No evidenced-by edges | Add evidence and link with evidenced-by |
| Strategy has no constraint_ids | UCAs not linked to hazard via violates | Add UCA→violates→hazard edges |
| Store locked error | Store not unlocked | Run `arch-assurance unlock` |
