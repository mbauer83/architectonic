# GRC Method Reference

## GRC in the STAMP Framework

In this platform, GRC is the **lifecycle manager** around constraints derived from STPA/CAST.
It is NOT a parallel silo — it builds on the same control-structure model.

The unified view:
- **STPA/STPA-Sec**: generates constraints (proactive)
- **CAST**: generates corrective constraints (reactive)
- **GRC**: governs (accountability), evaluates (risk), treats, and evidences (compliance)

The conceptual primitive is the **constraint**, not the risk. A safety constraint is valid
and must be enforced *independent* of any risk entity. This is the §2.1 anti-subordination
safeguard — risk never closes a safety obligation.

## Risk (ISO 31000)

ISO 31000 defines risk as "effect of uncertainty on objectives." In this platform:

- **`risk` entity** = the GRC overlay evaluating a hazard/loss-scenario (optional)
- **Attributes**: `likelihood`, `impact`, `risk_score`, `treatment`, `residual_*`, `review_date`
- **Connections**: `assesses → hazard/loss-scenario`; `treated-by → assurance-constraint`; `accountable-to → owner`

Treatment options (per ISO 31000):
- `mitigate` — reduce likelihood or impact
- `transfer` — shift risk to another party (insurance, contract)
- `avoid` — eliminate the risk source
- `accept` — tolerate residual risk (NOT valid for safety/security concern_class)

## Obligations and Compliance

An `obligation` entity represents a specific compliance instance:
- "Does our system satisfy clause 6-8 of ISO 26262?"
- The answer (status + evidence) is assurance-owned and confidential

The public framework catalog is referenced via the `cites` connection:
```
obligation → cites → scheme:code (e.g. ISO26262:6-8, GDPR:Art.5, EU-AI-ACT:Art.12)
```

The constraint → obligation link:
```
assurance-constraint → complies-with → obligation
```

This creates the chain: `loss → hazard → UCA → constraint → obligation → evidence`

## Key Standards

### ISO 31000:2018 — Risk Management
- §6.3 Context establishment
- §6.4 Risk assessment (identification + analysis + evaluation)
- §6.5 Risk treatment
- §6.6 Monitoring and review

### ISO/IEC 27001:2022 — Information Security Management
- Annex A: control categories (organizational, people, physical, technological)
- Statement of Applicability (SoA) maps to compliance-statement doc type

### EU AI Act (Regulation 2024/1689)
- Art. 9: Risk management system (mandatory for high-risk AI)
- Art. 12: Logging capability (≥6-month log retention)
- Art. 18: Technical documentation (10-year retention)
- Art. 26: Obligations for deployers of high-risk AI systems

### EU CRA (Cyber Resilience Act)
- Art. 13: Vulnerability handling; SBOM requirements (~Dec 2027)
- Art. 14: Reporting obligations (vulnerability reporting from Sep 2026)

### ISO/SAE 21434:2021 — Automotive Cybersecurity
- Clause 9: TARA (Threat Analysis and Risk Assessment)
- Clause 11: Cybersecurity incident response

## GRC vs Architecture Motivation Layer

**Never** model compliance obligations in ArchiMate's motivation layer.
- Architecture: requirements, goals, drivers (public, unclassified)
- Assurance: obligations, risks, constraints, evidence (confidential, in the assurance store)

The link is: `assurance-constraint → refines → ArchiMate-requirement`
The implementation: `requirement → realized-by → component/process`
This keeps the architecture model clean while maintaining full traceability.
