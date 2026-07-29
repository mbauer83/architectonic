---
name: grc-management
description: >
  Use this skill whenever the user is performing governance, risk, or compliance (GRC) work.
  Trigger on: "risk register", "risk assessment", "risk treatment", "compliance statement",
  "compliance obligation", "control coverage", "risk entity", "obligation entity",
  "ISO 31000", "ISO 27001", "GDPR compliance", "EU AI Act compliance", "CRA compliance",
  "grc-complete check", "coverage dashboard", "risk owner", "evidence links",
  "treat a risk", "accept a risk", "mitigate a risk", "obligation coverage",
  "create risk entity", "create obligation", "compliance gap", "risk heatmap",
  "risk register view", "control library". Also trigger when the user asks about
  assurance coverage, promotion safety checks, or compliance evidence traceability.
---

# GRC Management Skill

GRC (Governance, Risk, Compliance) is the lifecycle manager for assurance-constraints:
it governs (accountability), evaluates (risk), treats, and evidences (compliance).

GRC builds on the STPA/CAST analysis — constraints from those analyses flow into GRC.
All work goes through `assurance_*` MCP tools on the `arch-assurance-read` and
`arch-assurance-write` servers. Never edit the SQLCipher store directly.

---

## The GRC Loop

```
Hazard/Loss-Scenario → Risk (evaluate) → Treatment → Assurance-Constraint → Obligation (comply)
                                                            ↓
                                                    Evidence → Sign-off
```

### Step 1 — Evaluate Risk

Risk is **optional** — constraints are valid without a risk entity (§9 anti-subordination safeguard).
Create a risk entity to prioritise and track treatment.

```
assurance_create_node(node_type="risk", name="RSK-1: <brief description>",
                      attributes={"likelihood": "medium", "impact": "high",
                                  "risk_score": "high", "treatment": "mitigate",
                                  "review_date": "YYYY-MM-DD"})
assurance_add_edge(source_id=risk_id, target_id=hazard_id, conn_type="assesses")
assurance_add_edge(source_id=risk_id, target_id=constraint_id, conn_type="treated-by")
```

> **Safety/security constraints cannot be "closed" by a risk accept** — E506 blocks this.
> treatment=accept is only valid for non-safety concern_class.

Assign an owner to every risk:
```
assurance_add_edge(source_id=risk_id, target_id=role_node_id, conn_type="accountable-to")
```

### Step 2 — Define Compliance Obligations

An obligation represents "does our system comply with clause X of standard Y?"
Status and evidence are assurance-owned and confidential.

```
assurance_create_node(node_type="obligation",
                      name="OBL-1: ISO 26262:6-8 compliance",
                      attributes={"scheme": "ISO26262", "code": "6-8",
                                  "status": "in-progress"})
```

Link obligations to constraints (the constraint is what satisfies the obligation):
```
assurance_add_edge(source_id=constraint_id, target_id=obligation_id,
                   conn_type="complies-with")
```

W504 fires for obligations with no complies-with constraint — run `assurance_verify`.

### Step 3 — Add Evidence Links

Link constraints to their evidence artifacts (documents, test results, audit records):
```
assurance_add_edge(source_id=constraint_id, target_id=evidence_arch_id,
                   conn_type="evidenced-by")
```

> For architecture artifacts as evidence: use `assurance_register_arch_ref` for the
> one-way assurance→architecture reference, then reference the arch_id in the evidenced-by edge.

### Step 4 — Coverage and Gaps

Use the coverage tools to find what's incomplete:

```
assurance_grc_complete()     # §17(B) profile: obligations covered? risks treated?
assurance_coverage()         # Full gap dashboard across all concern types
assurance_risk_register()    # Tabular view of all risks
assurance_verify()           # §17(A) hard validity (E502–E505) + warnings (W502–W505)
```

### Step 5 — Promotion Preflight

Before promoting findings to a wider audience or enterprise tier:
```
assurance_promotion_preflight()   # Checks all safety/security constraints have owner + evidence
```

---

## Document Types

- **risk-assessment**: structured risk analysis with ISO 31000 sections
- **risk-treatment-plan**: approved treatments, implementation plan, residual risk, sign-off
- **compliance-statement**: obligation coverage, evidence summary, gaps, sign-off

Create these via the `artifact_create_document` tool on `arch-repo-write`.

---

## Gotchas

- **Safety/security constraints need owners** — E502 fires without an accountable-to connection.
- **risk.treatment=accept is blocked for safety hazards** — E506 enforces the safety-subordination safeguard.
- **W505 fires for risks without a treatment attribute** — always set treatment.
- **W504 fires for obligations with no complies-with** — link at least one constraint.
- **GRC is optional** — STPA/CAST constraints are valid and enforced with no risk entity.
  Risk *prioritises* treatment, it never closes a safety constraint.
- **Ask, don't assume TLP** — before setting TLP:AMBER or TLP:RED, confirm the sensitivity.
  Promotion of classified findings requires sign-off (§23 promotion gate).

---

## References

- See `skills/grc-management/references/grc-method.md` for GRC method concepts
- See `skills/grc-management/assets/risk-assessment-template.md` for the risk assessment template
- See `skills/grc-management/assets/compliance-statement-template.md` for the compliance statement template
- `assurance_guidance(topic="grc-risk")` and `(topic="grc-obligations")` for per-step coaching
- ISO 31000:2018 — Risk management guidelines
- ISO/IEC 27001:2022 — Information security management (Annex A controls)
- EU AI Act Art. 9 — Risk management system; Art. 12 — Logging; Art. 18 — Technical documentation
- EU CRA — Cybersecurity obligations (SBOM, vulnerability reporting)
