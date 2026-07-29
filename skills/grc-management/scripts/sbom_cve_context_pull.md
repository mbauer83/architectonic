# Script: SBOM / CVE Context Pull for GRC

**Purpose:** Contextualise external SBOM and CVE/vulnerability data against the
architecture model and STPA-Sec hazards to prioritise GRC remediation.

**When to run:** When ingesting a new SBOM build artefact, when a new CVE advisory
is published affecting a component in scope, or when refreshing the GRC risk register
with current vulnerability context.

---

## Step 1 — Ingest the SBOM

```
arch-assurance import-sbom <path/to/bom.cdx.json> \
  --anchor <arch-entity-id>   # the architecture entity this BOM belongs to
```

Or via MCP (for AI-agent orchestration):

```
assurance_import_bom(
  bom_data=<dict>,
  anchor_entity_id="<arch-entity-id>",
)
```

Re-ingestion is idempotent (keyed by anchor + BOM serialNumber + version).

---

## Step 2 — Set anchor mappings for key components

Map individual component PURLs to architecture entities once; mappings persist
and are applied automatically on future re-ingestion:

```
assurance_set_anchor(
  component_ref="pkg:pypi/requests@2.31.0",
  arch_entity_id="<arch-entity-id>",
  ref_type="purl",
)
```

---

## Step 3 — Ingest vulnerability data (OSV / NVD / CISA-KEV)

OSV-format records (from `osv.dev` or Dependency-Track export):

```
assurance_import_vulnerabilities(
  vuln_records=[
    {
      "id": "CVE-2026-xxxxx",
      "purl": "pkg:pypi/requests@2.31.0",
      "severity": "HIGH",
      "cvss_score": 7.5,
      "summary": "...",
      "vex_status": "affected",
    }
  ],
  source="osv",
)
```

For Dependency-Track: export the findings JSON and pass the list directly.

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
- If not, create one: `assurance_create_node('risk', ...)` with `treatment` and owner.
- Update `treated-by` links to existing `assurance-constraint` entities.
- Add evidence: `evidenced-by` edge from the constraint to the CVE finding record.

---

## Step 6 — Check coverage

```
assurance_grc_complete()    # GRC coverage profile
assurance_coverage()        # gap dashboard
assurance_aibom_coverage()  # AI-BOM marking gaps
```

---

## Automation path (CI integration)

Post SBOMs from the build pipeline to the REST endpoint (when a
network-reachable store is configured):

```yaml
# GitHub Actions example
- name: Upload SBOM to assurance store
  run: |
    curl -X POST $ARCH_BACKEND_URL/api/assurance/sbom \
      -H "Authorization: Bearer $ARCH_ASSURANCE_TOKEN" \
      -H "Content-Type: application/json" \
      --data-binary @sbom.cdx.json
```

Local/SQLCipher users use rungs 1–2 (GUI upload or `arch-assurance import-sbom`).
Network-reachable stores (PocketBase / Supabase) support the CI rungs.

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
