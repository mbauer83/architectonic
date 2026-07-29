---
name: cast-investigation
description: >
  Use this skill whenever the user is conducting a CAST (Causal Analysis using System Theory)
  investigation of an actual incident or accident. Trigger on: "investigate incident",
  "CAST analysis", "accident investigation", "what caused the incident", "causal analysis",
  "incident post-mortem", "learn from accident", "corrective actions", "observed control flaws",
  "seal baseline", "analysis baseline", "cast-complete check", "create incident entity",
  "CAST investigation document". Also trigger when the user asks to trace observed UCAs to
  an incident or to derive corrective constraints from an investigation.
---

# CAST Investigation Skill

CAST is the **reactive** counterpart of STPA on the **same** STAMP control-structure model.
It reconstructs the control structure as-existed at the incident, identifies control flaws,
and derives corrective constraints that enter the GRC lifecycle.

All assurance work goes through `assurance_*` MCP tools. Never edit the SQLCipher store directly.

---

## The Five-Step CAST Method

### Step 1 — Create the Incident Entity

An incident anchors the investigation. It represents the actual occurred loss event.

```
assurance_create_node(node_type="incident", name="INC-1: <brief description>",
                      concern_class="safety")  # or security/operational
```

> **Ask, don't assume**: Confirm the incident date and concern_class before creating.

### Step 2 — Seal an Analysis Baseline (REQUIRED — G-g gate)

CAST reconstructs the control structure as-existed *at the incident*. A sealed baseline
pins the model state and makes the investigation reproducible and audit-defensible (§10).

```
assurance_seal_baseline(notes="CAST baseline for INC-1: <date>", analysis_id="INC-1")
```

**This must be done before creating observed UCAs/scenarios.**
`assurance_cast_complete` will fail (G-g) if incidents exist without a baseline.

### Step 3 — Reconstruct the Control Structure As-Existed

Connect the incident to the control structure nodes and hazards it touched via `investigates`.

```
assurance_add_edge(source_id=incident_id, target_id=csn_id, conn_type="investigates")
assurance_add_edge(source_id=incident_id, target_id=hazard_id, conn_type="investigates")
```

Mark UCAs and loss-scenarios as observed (mode=observed in attributes):

```
assurance_create_node(node_type="unsafe-control-action", name="UCA-OBS-1: ...",
                      uca_type="not-provided", concern_class="safety",
                      attributes={"mode": "observed"})
assurance_add_edge(source_id=uca_id, target_id=ca_id, conn_type="concerns")
assurance_add_edge(source_id=uca_id, target_id=hazard_id, conn_type="violates")
```

### Step 4 — Identify Causal Scenarios and Corrective Actions

Create loss-scenarios with mode=observed and corrective-action entities.

```
assurance_create_node(node_type="loss-scenario", name="LS-OBS-1: ...",
                      attributes={"mode": "observed"})
assurance_add_edge(source_id=ls_id, target_id=uca_id, conn_type="explains")

assurance_create_node(node_type="corrective-action", name="CRA-1: ...")
```

### Step 5 — Derive Corrective Constraints

Corrective actions must derive assurance-constraints that enter the GRC lifecycle.

```
assurance_create_node(node_type="assurance-constraint", name="ACN-CRA-1: ...",
                      concern_class="safety", disposition="controlled-with-evidence")
assurance_add_edge(source_id=incident_id, target_id=acn_id, conn_type="derives")
assurance_add_edge(source_id=cra_id, target_id=acn_id, conn_type="derives")
assurance_add_edge(source_id=ls_id, target_id=acn_id, conn_type="derives")
```

---

## Coverage Check

`assurance_cast_complete` runs the §17(B) cast-complete profile. Checks:
- A sealed analysis_baseline exists (G-g gate — fails if missing)
- Every incident has ≥1 investigates edge
- Every corrective-action has ≥1 derives edge to a constraint

Fix all gaps before declaring the investigation complete.

---

## Gotchas

- **Seal the baseline before creating observed UCAs** — the baseline pins "as-existed" state.
  `assurance_cast_complete` (G-g) blocks completion without it.
- **Use mode=observed in attributes** for UCAs and loss-scenarios found in CAST
  (vs mode=hypothesized for STPA). Pass `attributes={"mode": "observed"}` to `assurance_create_node`.
- **E505 fires if an incident has no investigates edge** — always connect the incident to
  the CSN or hazard it touched.
- **Corrective constraints enter the same GRC lifecycle** — they need concern_class, owner,
  and evidence just like STPA constraints. Run `assurance_verify` to catch E502/W502.
- **CAST and STPA share the control structure model** — reuse existing CSNs; don't duplicate them.

---

## References

- See `skills/cast-investigation/references/cast-method.md` for CAST method concepts
- See `skills/cast-investigation/assets/cast-investigation-template.md` for the doc template
- `assurance_guidance(topic="cast-investigation")` for per-step coaching
- Cross-reference `skills/stpa-analysis/` for shared control-structure concepts
- CAST Handbook (Leveson) via STPA Handbook §5 — https://www.flighttestsafety.org/images/STPA_Handbook.pdf
- STAMP/STPA/CAST overview (UL) — https://www.ul.com/sis/blog/introduction-to-stamp-stpa-and-cast
