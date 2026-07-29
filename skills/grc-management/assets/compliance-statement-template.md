---
title: "Compliance Statement: [Framework] — [System Name]"
doc_type: compliance-statement
status: draft
framework: "[e.g. ISO26262 | ISO27001 | EU-AI-Act | GDPR | CRA]"
version: "[framework version or year]"
assessment_date: "YYYY-MM-DD"
---

# Compliance Statement: [Framework] — [System Name]

## Scope

_What system, product, or service is this compliance statement for?
What version/configuration is in scope?_

- **System:** [name]
- **Version / configuration:** [describe]
- **Assessment date:** YYYY-MM-DD
- **Assessor:** [name/role]
- **Framework:** [full name, version]

## Applicable Obligations

_List the obligations in scope. Each should have an `obligation` entity in the assurance store._

| Obligation ID | Framework Clause | Name | Status |
|---|---|---|---|
| OBL@… | [e.g. ISO26262:6-8] | [clause name] | [in-progress / compliant / non-compliant / N/A] |

## Control Coverage

_For each obligation, which assurance-constraints satisfy it? What is the evidence?_

| Obligation ID | Satisfying Constraints | Evidence | Owner | Gap? |
|---|---|---|---|---|
| OBL@… | ACN@… | [doc/artifact reference] | [owner] | [Y/N] |

> Constraints satisfy obligations via the `complies-with` edge:
> `assurance-constraint → complies-with → obligation`

## Evidence Summary

_Where is the evidence? Summarise by category._

| Evidence Type | Location | Covers |
|---|---|---|
| Test results | [path/link] | ACN@… |
| Audit records | [path/link] | OBL@… |
| Design documents | [path/link] | ACN@… |

## Gaps and Exceptions

_List any obligations that are not fully satisfied. Include justification and remediation plan._

| Obligation ID | Gap Description | Justification | Remediation Target |
|---|---|---|---|
| OBL@… | [what is missing] | [why it exists] | YYYY-MM-DD |

## Sign-off

_This compliance statement requires formal sign-off by an accountable party._

| Role | Name | Date | Signature |
|---|---|---|---|
| Assessment Owner | | YYYY-MM-DD | |
| Technical Authority | | YYYY-MM-DD | |
| Compliance Officer | | YYYY-MM-DD | |

## References

- [Framework reference]: [URL or document reference]
- STPA analysis: [link to stpa-analysis doc]
- Risk assessment: [link to risk-assessment doc]
- Assurance store baselines: [baseline IDs]
