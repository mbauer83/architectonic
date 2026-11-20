# Script: SBOM / CVE Context Pull for GRC

**Purpose:** Contextualise external SBOM and CVE/vulnerability data against the
architecture model and STPA-Sec hazards to prioritise GRC remediation.

**When to run:** When ingesting a new SBOM build artefact, when a new CVE advisory
is published affecting a component in scope, or when refreshing the GRC risk register
with current vulnerability context.

---

## Step 1 — Ingest the SBOM and its advisories

One call ingests a CycloneDX BOM for one architecture anchor, optionally with the OSV
advisory records for its components. It produces a new active signal snapshot that
supersedes the anchor's previous one:

```
assurance_ingest_security_signals(
  anchor_entity_id="<arch-entity-id>",   # the architecture entity this BOM belongs to
  bom=<parsed CycloneDX 1.x JSON document>,
  vulnerabilities=[<OSV record>, ...],   # optional; each needs "id" and "affected"
  source="osv",                          # optional
  request_id="<idempotency key>",        # optional
)
```

Resubmitting the same `request_id` with the same payload returns the original outcome and
writes nothing. Without a `request_id` every call ingests anew.

Each advisory is matched to its component by package identity and version range. Advisories
that do not apply are excluded and counted, not stored as findings. Omit `vulnerabilities`
for a BOM-only inventory snapshot.

The GUI offers the same ingest on the anchor entity's page.

---

## Step 2 — Read what was ingested

```
assurance_list_bom_components(anchor_entity_id="<arch-entity-id>")
assurance_security_metrics(anchor_entity_id="<arch-entity-id>")
assurance_security_stats()
```

---

## Step 3 — Trace one advisory to what it affects

```
assurance_vulnerability_impact(identifier="CVE-2026-xxxxx")
```

---

## Step 4 — Contextualise against STPA-Sec hazards

Query the vulnerability findings for an affected component:

```
assurance_list_vulnerabilities(purl="pkg:pypi/requests@2.31.0")
```

For each HIGH/CRITICAL finding on a component that is:
- Referenced by a `control-structure-node` (via `binds-to` arch ref), or
- An architecture entity linked to a `hazard` with `concern_class=security`,

→ Create or update a `loss-scenario` entity linking the CVE finding to the
  existing hazard, using `assurance_create_node` + `assurance_add_edge`.

---

## Step 5 — Update GRC risk register

For each contextualised hazard with new vulnerability evidence:
- Check whether a `risk` entity exists (`assurance_list_nodes(node_type='risk')`).
- If not, create one: `assurance_create_node(analysis_id=..., node_type='risk', ...)` with a
  `treatment` attribute, and give it an owner (`accountable-for` from a control-structure node).
- Update `treated-by` links to existing `assurance-constraint` entities.
- Add evidence: create an `evidence` node that records the finding, and link it with an
  `evidenced-by` edge from the constraint.

---

## Step 6 — Check coverage

```
assurance_grc_complete()    # GRC coverage profile
assurance_coverage()        # gap dashboard
artifact_aibom_coverage()   # AI-BOM marking gaps (on arch-repo-read)
```

---

## Automation path (CI integration)

Post SBOMs from the build pipeline to the REST endpoint of a backend the pipeline can
reach. The anchor is the path, and the body wraps the BOM:

```yaml
# GitHub Actions example
- name: Upload SBOM to assurance store
  run: |
    jq '{bom: .}' sbom.cdx.json | curl -X POST \
      "$ARCH_BACKEND_URL/api/assurance/arch-artifacts/$ANCHOR_ENTITY_ID/security-snapshots" \
      -H "Content-Type: application/json" \
      --data-binary @-
```

The body also accepts `vulnerabilities`, `source` and `request_id`, with the same meaning
as the MCP tool's arguments.

---

## AI-BOM round-trip (for agentic systems)

```
# Export modeled AI inventory
assurance_aibom_export(ai_components=[...])

# Reconcile against runtime discovery
assurance_reconcile_aibom(
  modeled_components=[...],
  discovered_components=[...],   # from Qualys TotalAI / MS Defender output
)
```

Drift report shows components in production not yet modeled → create modeling tasks.
