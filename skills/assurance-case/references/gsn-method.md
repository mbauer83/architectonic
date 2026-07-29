# GSN Method Reference

## GSN Notation

Goal Structuring Notation (GSN) is a graphical argument notation for assurance cases.
It externalises the argument structure so it can be reviewed, challenged, and updated.

### Node Types

| GSN Symbol | Type          | Meaning                                      | PUML shape  |
|------------|---------------|----------------------------------------------|-------------|
| G          | goal          | A claim that must be argued                  | rectangle   |
| S          | strategy      | How the argument is decomposed               | card        |
| Sn         | solution      | Evidence — a reference to an artefact        | database    |
| C          | context       | Contextual information or scope              | usecase     |
| A          | assumption    | An assumed truth (not argued)                | usecase     |
| J          | justification | A rationale for a strategy or context        | usecase     |

### Connection Types

| Connection      | Meaning                                          | Direction        |
|-----------------|--------------------------------------------------|------------------|
| supported-by    | Goal/strategy decomposes into sub-goals/solutions| parent → child   |
| in-context-of   | Context/assumption applies to goal/strategy      | goal → context   |

### Completeness Rules

An argument is **complete** when:
1. Every goal is either directly supported by solutions (Sn) or decomposed via a strategy (S)
2. Every strategy has at least one sub-goal
3. No goal is "undeveloped" (i.e., has no `supported-by` connections)
4. Every Sn has a referenced evidence artefact

---

## STPA → GSN Mapping

STPA produces exactly the material needed to populate a GSN assurance case:

| STPA artefact          | GSN element              | Rationale                                      |
|------------------------|--------------------------|------------------------------------------------|
| Loss                   | Top Goal (G)             | Overall safety/security claim to prevent losses|
| Hazard                 | Sub-Goal (G)             | "Hazard H is controlled"                       |
| Constraint derivation  | Strategy (S)             | Argument by constraint derivation from UCAs    |
| Assurance constraint   | Sub-Goal (G) or Strategy | Concrete claim that constraint holds           |
| Evidence artefact      | Solution (Sn)            | Test report, audit record, formal proof        |
| Concern class context  | Context (C)              | "In the context of safety/security concern X"  |
| Analysis scope         | Assumption (A)           | "Assuming environment conditions Y"            |

### Standard STPA-Derived GSN Pattern

```
G-TOP: "The system prevents [all losses]"
  ├─ S-STRATEGY: "Argument by STPA hazard decomposition"
  │     ├─ G-H1: "Hazard H1 is controlled"
  │     │     ├─ S-H1: "Argument by constraint derivation from UCAs violating H1"
  │     │     │     ├─ G-C1: "Constraint C1 holds" ──Sn-E1: evidence
  │     │     │     └─ G-C2: "Constraint C2 holds" ──Sn-E2: evidence
  │     │     └─ C-H1: "In context of [concern class]"
  │     └─ G-H2: "Hazard H2 is controlled" ...
  └─ A-SCOPE: "Assuming [analysis scope]"
```

### Evidence Types (Sn nodes)

Evidence artefacts that typically appear as Sn nodes:

- Test reports (unit, integration, system-level)
- Formal verification proofs
- Safety review records (FMEA, FTA, HAZOP)
- Audit certificates (ISO 26262, IEC 62443, SOC 2)
- Model-based analysis results
- Penetration test reports
- Code coverage metrics
- Regulatory approval letters

---

## GSN Patterns for STPA-Derived Arguments

### Pattern 1: Single Hazard with Full Chain

Applicable when one hazard, one UCA, one constraint, one evidence artefact:

```
G1 [H controlled] --supported-by--> S1 [Argument by CA derivation]
S1 --supported-by--> G2 [Constraint C holds]
G2 --supported-by--> Sn1 [Test report T-001]
G1 --in-context-of--> C1 [Safety concern context]
```

### Pattern 2: Multiple Hazards with Shared Strategy

```
G-TOP --supported-by--> S-OVERALL [Argument by hazard decomposition]
S-OVERALL --supported-by--> G-H1 [H1 controlled]
S-OVERALL --supported-by--> G-H2 [H2 controlled]
```

### Pattern 3: Unresolved Gap (Open Sub-Goal)

An undeveloped goal is shown with a diamond marker in formal GSN tools.
In this system, gaps appear in the `assurance_draft_gsn` response under `gaps`.
Open sub-goals are **certification blockers** — close them before sign-off.

---

## Standards and References

- GSN Community Standard v3 (Goal Structuring Notation, 2021)
- SACM v2.2 — OMG Structured Assurance Case Metamodel
- DO-178C §12 — Software Life Cycle Data (aviation)
- ARP4761 §A.4 — Safety Assessment Process (aerospace)
- IEC 62443-4-1 SR 2.13 — Security Case (industrial control)
- ISO 26262 Part 2 §6.4.9 — Functional safety argument
- EU AI Act Annex IV — Technical documentation requirements
