---
name: assurance-case
description: >
  Use this skill whenever the user is building or reviewing an assurance case, working with
  GSN (Goal Structuring Notation), creating a safety case or security case, checking argument
  completeness, or using any of these terms: "assurance case", "GSN", "safety case",
  "security case", "argument completeness", "assurance_draft_gsn", "assurance_case_completeness",
  "goal structuring notation", "top goal", "sub-goal", "solution node", "bowtie diagram",
  "claim evidence argument", "open sub-goal", "evidence gap". Also trigger when the user
  asks to create an assurance-case document, a gsn diagram, or a bowtie diagram.
---

# Assurance Case Skill

All assurance work goes through the `assurance_*` MCP tools on the
`arch-assurance-read` and `arch-assurance-write` servers. Never edit the
SQLCipher store directly. Gate with `assurance_store_status` if store state is uncertain.

---

## Method Overview

An assurance case is a structured argument, supported by evidence, that a system
satisfies its safety/security claims in its intended context of use. The argument
is expressed in GSN (Goal Structuring Notation):

| Symbol | Meaning | PUML shape |
|--------|---------|-----------|
| G      | Goal — a claim to be argued | rectangle |
| S      | Strategy — how the argument proceeds | card (parallelogram) |
| Sn     | Solution — evidence node | database |
| C      | Context — scope or assumption | usecase (rounded) |
| A      | Assumption | usecase |
| J      | Justification | usecase |

Connections: `supported-by` (goal decomposition, solid arrow), `in-context-of` (context, dashed).

---

## Standard Workflow

### Step 1 — Draft the GSN skeleton

Call `assurance_draft_gsn` to scaffold the argument from existing STPA content:

```
assurance_draft_gsn()
```

Inspect the returned dict:
- `top_goal` — overall safety/security claim derived from losses
- `sub_goals` — one per hazard
- `strategies` — "Argument by constraint derivation" for each hazard
- `solutions` — evidence artifacts already linked via `evidenced-by`
- `gaps.constraints_without_evidence` — constraints needing evidence
- `gaps.hazards_without_constraints` — hazards needing UCA analysis

### Step 2 — Review and close gaps

For each gap in `constraints_without_evidence`:
```
assurance_add_edge(source_id=constraint_id, target_id=evidence_ref_id, conn_type="evidenced-by")
```

For each gap in `hazards_without_constraints`:
- Complete STPA UCA analysis for the hazard (see stpa-analysis skill)
- Derive and link constraints via `derives` edges

### Step 3 — Create the GSN diagram

Create a `gsn` diagram artifact with the scaffolded nodes and edges.
Use `gsn_type` values: "goal", "strategy", "solution", "context", "assumption", "justification".
Use `conn_type` values: "supported-by", "in-context-of".

```
artifact_create_diagram(diagram_type="gsn", name="...", diagram_entities={
    "nodes": [...],
    "edges": [...]
})
```

### Step 4 — Produce the assurance-case document

Create an `assurance-case` document using `artifact_create_document`.
Use `claim_type`: "safety", "security", or "combined".
Required sections: Purpose and Scope, Safety/Security Claims, GSN Argument Structure,
Evidence Summary, Argument Completeness, Sign-off, References.

See `assets/assurance-case-template.md` for the full template.

### Step 5 — Run completeness check

```
assurance_case_completeness()
```

All three checks must pass before sign-off:
- `constraint_has_evidence` — every assurance-constraint has ≥1 `evidenced-by` edge
- `hazard_has_constraint` — every hazard has ≥1 constraint via UCA derives chain
- `loss_has_hazard` — every loss has ≥1 hazard via `leads-to`

---

## Gotchas

- `assurance_draft_gsn` reads from the live store — complete STPA analysis first
- Bowtie diagrams (use `bowtie` type) are for stakeholder communication; GSN is the formal argument
- The `status` field on an assurance-case document must be "complete" before sign-off
- `assurance_case_completeness` checks argument structure only; run `assurance_verify` for hard rules
- Constraints inherited from CAST corrective-actions also count as evidence chains — check both
- For combined claim_type, run both `assurance_stpa_complete` and `assurance_grc_complete` first

---

## Reference Files

- `references/gsn-method.md` — full GSN notation reference and STPA→GSN mapping
- `assets/assurance-case-template.md` — assurance-case document template
- `scripts/draft_gsn_from_hazards.md` — walkthrough of assurance_draft_gsn
- `scripts/completeness_check.md` — walkthrough of assurance_case_completeness
