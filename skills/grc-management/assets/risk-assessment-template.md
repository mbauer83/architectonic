---
title: "Risk Assessment: [System/Scope Name]"
doc_type: risk-assessment
status: draft
scope: "[brief scope description]"
framework: ISO31000
---

# Risk Assessment: [System/Scope Name]

## Scope and Context

_What system, process, or scope is being assessed? Who are the stakeholders?
What losses (from STPA) does this assessment address?_

- **Assessment scope:** [describe]
- **Losses in scope:** LSS@… [loss name]
- **Assessment date:** YYYY-MM-DD
- **Assessor:** [name/role]
- **Framework:** ISO 31000:2018

## Risk Identification

_What risks exist? Each risk entity should `assesses` a hazard or loss-scenario._

| Risk ID | Name | Hazard/Scenario Assessed | Concern Class |
|---|---|---|---|
| RSK@… | [name] | HAZ@… / LSC@… | [safety / security / operational] |

## Risk Analysis

_For each identified risk: what is the likelihood and impact?_

| Risk ID | Likelihood | Impact | Risk Score | Rationale |
|---|---|---|---|---|
| RSK@… | [low/medium/high] | [low/medium/high] | [low/medium/high] | [why] |

> For safety/security risks: the risk score informs priority but never justifies
> accepting a safety/security constraint without proper controls (the safety-subordination safeguard).

## Risk Evaluation

_Which risks require treatment? Which are tolerable?_

| Risk ID | Decision | Rationale | Priority |
|---|---|---|---|
| RSK@… | [treat / tolerate] | [why] | [high / medium / low] |

## Risk Treatment

_How will each risk be treated? Link to treating constraints._

| Risk ID | Treatment | Treating Constraints | Owner | Review Date |
|---|---|---|---|---|
| RSK@… | [mitigate / transfer / avoid / accept] | ACN@… | [owner] | YYYY-MM-DD |

> **Note:** `accept` treatment is not permitted for safety/security concern_class (E506).

## Monitoring and Review

_How will risks be monitored? When will this assessment be reviewed?_

- **Review schedule:** [quarterly / annually / on incident]
- **Review owner:** [name/role]
- **Trigger for early review:** [significant architecture change / new incident / regulatory update]

## References

- ISO 31000:2018 Risk management guidelines
- STPA analysis results: [link to stpa-analysis doc]
- Relevant losses: LSS@…
