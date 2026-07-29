---
name: stpa-analysis
description: >
  Use this skill whenever the user is performing safety or security analysis using STPA
  or STAMP, or any request involving: "identify losses", "model control structure",
  "add UCA", "run STPA", "conduct STPA analysis", "unsafe control actions",
  "derive safety constraints", "derive security constraints", "STPA-Sec", "STAMP analysis",
  "control action", "loss scenario", "system hazard", "assurance constraint",
  "safety constraint", "model this controller", "bind a CSN node", "stpa complete check",
  "CAST investigation", "incident analysis". Also trigger when the user asks to create or
  view a control-structure diagram, a UCA matrix, or when they use the assurance MCP tools
  (assurance_create_node, assurance_add_edge, assurance_stpa_complete, assurance_model_this).
---

# STPA Analysis Skill

All assurance work goes through the `assurance_*` MCP tools on the
`arch-assurance-read` and `arch-assurance-write` servers. Never edit the
SQLCipher store directly. Gate with `assurance_store_status` if store state is uncertain.

---

## The Four-Step STPA Method

### Step 1 — Identify Losses

Losses are unacceptable outcomes stakeholders must avoid (injury, data breach,
mission failure, regulatory violation). Start broad; refine iteratively.

```
assurance_create_node(node_type="loss", name="Loss of X", concern_class="safety")
```

Every hazard and constraint must trace back to a loss.

### Step 2 — Identify System-Level Hazards

A hazard is a system state that, combined with worst-case environment, leads to a loss.

```
assurance_create_node(node_type="hazard", name="System in state X", concern_class="safety")
assurance_add_edge(source_id=hazard_id, target_id=loss_id, conn_type="leads-to")
```

W503 fires for hazards with no `leads-to` loss — run `assurance_verify`.

### Step 3 — Model the Control Structure

The control structure is a hierarchy of controllers and controlled processes
connected by control actions and feedback.

```
assurance_create_node(node_type="control-structure-node", name="ECU",
                      node_role="controller", binding_status="unbound-pending")
assurance_create_node(node_type="control-action", name="Throttle Command")
assurance_add_edge(source_id=csn_id, target_id=ca_id, conn_type="issues")
assurance_add_edge(source_id=ca_id, target_id=process_id, conn_type="acts-on")
assurance_add_edge(source_id=process_id, target_id=csn_id, conn_type="feedback")
```

Use `assurance_model_this` to bind unbound-pending nodes to architecture entities.

### Step 4 — UCAs, Loss Scenarios, and Constraints

For each control action, apply the four guidewords: not-provided, provided-when-unsafe,
wrong-timing, stopped-too-soon.

```
assurance_create_node(node_type="unsafe-control-action", name="UCA-1: ...",
                      uca_type="not-provided", concern_class="safety")
assurance_add_edge(source_id=uca_id, target_id=ca_id, conn_type="concerns")
assurance_add_edge(source_id=uca_id, target_id=haz_id, conn_type="violates")
assurance_create_node(node_type="loss-scenario", name="LS-1: ...")
assurance_add_edge(source_id=ls_id, target_id=uca_id, conn_type="explains")
assurance_create_node(node_type="assurance-constraint", name="ACN-1: ...",
                      concern_class="safety", disposition="controlled-with-evidence")
assurance_add_edge(source_id=uca_id, target_id=acn_id, conn_type="derives")
assurance_add_edge(source_id=ls_id, target_id=acn_id, conn_type="derives")
```

Run `assurance_stpa_complete` to verify all chains are connected.

---

## Coverage Check

`assurance_stpa_complete` runs the §17(B) profile. Checks:
- Every hazard has ≥1 `leads-to` loss
- Every UCA has ≥1 `concerns` control-action AND ≥1 `violates` hazard
- Every loss-scenario has ≥1 `explains` UCA
- Every UCA and loss-scenario has ≥1 `derives` constraint

Fix all gaps before declaring analysis complete.

---

## Binding Workflow (assurance_model_this)

When a CSN has `binding_status=unbound-pending`:
1. Call `assurance_model_this(assurance_node_id, suggested_arch_type, suggested_name)`
2. Execute the returned three-step task spec:
   - Step 1: `artifact_create_entity` on arch-repo-write (dry_run=true first)
   - Step 2: `assurance_register_arch_ref` with the returned entity_id
   - Step 3: `assurance_edit_node(binding_status="bound")`

Never set `binding_status="bound"` without completing the arch-ref registration.

---

## Gotchas

- **Ask, don't assume concern_class.** Always confirm safety/security/privacy/operational
  before creating nodes — it drives E502/E503 validation rules.
- **UCA must reference exactly one control-action** via `concerns` edge. E501 fires otherwise.
- **Safety/security constraints cannot use `disposition=accepted`** — E503 blocks this.
  Use `eliminated`, `prevented-by-design`, `controlled-with-evidence`, or `alarp-justified`.
- **`assurance_model_this` returns a task spec, not an action.** Execute all three steps.
- **Run `assurance_verify` before `assurance_stpa_complete`** — §17(A) hard errors and
  §17(B) coverage gaps are separate checks.

---

## References

- See `skills/stpa-analysis/references/stpa-method.md` for STPA method concepts
- See `skills/stpa-analysis/assets/stpa-analysis-template.md` for the doc template
- `assurance_guidance(topic="stpa-losses")` through `"stpa-constraints"` for per-step coaching
- STPA Handbook (Leveson & Thomas) — https://www.flighttestsafety.org/images/STPA_Handbook.pdf
- ISO/SAE 21434 Clause 9 (TARA) — the security parallel (STPA-Sec)
