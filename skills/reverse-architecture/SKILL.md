---
name: reverse-architecture
description: >
  Use this skill whenever the user wants to reverse-engineer infrastructure-as-code (Terraform,
  Pulumi, CloudFormation, Bicep, etc.) into ArchiMate 4.0 model entities, connections, and
  diagrams. Trigger on phrases like "map terraform to the model", "reverse architect this
  infrastructure", "analyse the terraform and update the architecture", "what ArchiMate entities
  should I create for this terraform", "sync the architecture with the infra code",
  "create technology domain entities from the terraform", "model this cloud infrastructure",
  or any request that combines reading IaC code with creating or updating architectural model
  content. Also trigger when the user gives a path to a terraform project and asks what to
  do with it architecturally, or when they say "the terraform has changed, update the model".
---

# Reverse Architecture — IaC → ArchiMate 4.0

## Phase 1 — Get live authoring guidance

Call these two tools first, before reading any IaC:

```
artifact_authoring_guidance(filter=["technology"])
artifact_authoring_guidance(filter=["common"])
```

Read the output. It is authoritative. The type mappings below are judgment supplements — they do not override what the live guidance says.

---

## Phase 2 — Read and categorise the IaC

Read all `.tf` files in the target project and any sibling projects (shared DNS, IAM, networking often live in a `general` or `shared` sibling directory).

Use the Read tool to read files. When Bash `find` is unavailable, probe common numbered prefixes: `00_`, `10_`, `20_`, `30_`, `31_`, `40_`, `50_`, `60_`, `65_`, `70_`, `80_`, `90_`, then `main.tf`, `variables.tf`, `outputs.tf`.

The live authoring guidance gives you the type mappings. Apply the following judgment rules where the guidance is silent or ambiguous:

**Granularity — many identical sub-resources (e.g. 35 databases on one server):**
Do not create individual `artifact` entities upfront. Create the server as `system-software`. Add individual database `artifact` entities only when a corresponding `application-component` exists to connect to, or when a specific compliance/isolation question targets that database. Use the server entity's Properties table to list the databases and their count. This is the correct application of the `never_create_when` rule — bulk artifacts with no connections serve no architectural question.

**Resource groups and IAM perimeters → `grouping`:**
Azure Resource Groups, AWS accounts/VPCs-as-boundaries, GCP projects, and IAM perimeters are logical aggregation scopes, not infrastructure nodes. Model them as `grouping` entities. Resolve computed names (e.g. `lower("${project}-${environment}")`) to their actual values. Link each member entity to its grouping via `archimate-aggregation`. The Velero/backup RG and similar cross-cutting groups each get their own `grouping`. Do NOT use `technology-node` for resource groups.

**Cloud regions → `location`:**
Model cloud provider regions (e.g. West Europe, Central US) as `location` entities when the region is a meaningful architectural boundary — data residency, disaster-recovery topology, or separate traffic zones. Create one `location` per distinct region present in the IaC; do not create per-environment duplicate locations. Link resident entities via `archimate-aggregation` from the location. Do not model availability zones as separate locations unless they are architecturally distinct (cross-AZ DR is a property on the cluster/server entity, not a separate location).

**Storage accounts, object storage, blob stores → `system-software`:**
Cloud storage services (Azure Storage Accounts, AWS S3, GCS Buckets) are managed platform services. Model them as `system-software`, not `artifact`. Use `artifact` only for files or packages stored *within* a storage service when a specific compliance or traceability question targets the individual file.

**Service principals and managed identities → `system-software`:**
Model ALL service principals and managed identities that appear in the IaC, including AKS/cluster SPs. Apply the disambiguation:
- Provides platform auth or managed identity for infrastructure automation → `system-software`
- Delivers user-facing business behaviour (gateway, API, frontend) → `application-component`
When uncertain, prefer `system-software` and note the ambiguity.

**Kubernetes node pools vs cluster node:**
Node pools (named pools with specific VM SKUs, e.g. `Standard_D2ads_v5`) → `device`, not `system-software`. The cluster itself is the `technology-node`; pools are the specific virtualized hardware within it. Name pools after their terraform `name` field (e.g. `name = "standard"` → "[Env] Standard Node Pool"), not after a functional role you invent. The default/system pool is the AKS system node pool; named pools in `node_pools` are workload pools.

**Kubernetes runtime vs cluster node:**
Do not create a separate "Kubernetes Runtime" `system-software` entity when the AKS/EKS/GKE cluster is already modelled as a `technology-node`. The cluster node implicitly contains its orchestration layer. Only create a separate runtime entity if a specific architectural question targets the K8s version or API surface independently.

**Public IPs and ingress endpoints → `technology-interface`:**
Static public IP addresses and DNS-fronted ingress endpoints (e.g. Traefik load balancer IPs) are external-facing access points. Model each as `technology-interface`. Include the IP address and FQDN/domain-name-label in properties. Connect via `archimate-serving` from the cluster's ingress controller to the interface, and via `archimate-serving` from the interface to the DNS zone(s) that resolve to it.

**DNS zones → `communication-network`:**
Model each DNS zone as a `communication-network`. Record the hosted CNAMEs and A records as a property list — individual DNS records are not separate entities unless a specific compliance or routing question targets them. Connect ingress interfaces to their DNS zones via `archimate-serving`.

**Environment granularity:**
Model once (with environment noted in properties) unless environments differ architecturally in structure, not just in scale.

**What not to model:**
Terraform backend state storage, role assignments, tags, lifecycle rules, diagnostic settings, Terraform lock containers, VNet/subnet resources that are fully managed inside a Kubernetes or PaaS module with no architectural decisions exposed (include CIDR ranges as properties on the cluster or region entity instead).

---

## Phase 3 — Check the existing model

Before proposing anything:

```
artifact_query_list_artifacts(domain="technology")
artifact_query_list_artifacts(domain="common")
```

Then run 2–3 targeted searches per proposed entity using different terms (resource name, provider shorthand, functional role synonym). Read any partial matches in full. Decide: exact match (reuse), partial match (update), name collision (new), or no match (new).

---

## Phase 4 — Propose before acting

Present a structured proposal with these sections:

- **New entities** — type, name, terraform source, one-line rationale
- **Entities to update** — artifact ID, what changes, why
- **New connections** — source → type → target, one-line rationale
- **Diagram proposals** — title, audience, architectural question answered

Evaluate proposed diagrams against the stakeholder diagram requirements:
- All relevant network segments (VNets, subnets where architecturally meaningful)
- All load balancers and their assignment to services
- All static IP addresses and CIDR ranges
- All DNS zones and key hostnames
- All availability zones / regions
- All external dependencies (third-party services, external APIs)
- All infrastructure resources (servers, databases, storage)
- All relevant inbound/outbound ports per resource (as connection or entity properties)
- All traffic paths with direction and protocol identifiable

Ask for confirmation before Phase 5. A small change (2–3 entities) can proceed with a brief statement; a large batch warrants explicit approval.

---

## Phase 5 — Execute approved changes

1. Dry-run each entity/connection (`dry_run=true`). Read the preview.
2. Batch with `artifact_bulk_write` for multi-entity creates.
3. Search for duplicates before each create.
4. Commit (`dry_run=false`). Report artifact IDs.
5. Verify: `artifact_verify(repo_scope="engagement", return_mode="full")`. Fix errors.
6. Save: `artifact_save_changes()`.

---

## Naming and content

Names: descriptive, technology-agnostic. "Production Kubernetes Cluster" not "module.aks". Prefix environment when modelled per-environment; use the environment name from IaC locals (e.g. `environment = "Production"` → "Production …").

Summary: one sentence — what the element *is* and its *architectural role*.

Properties: always include `Terraform source` citing the exact relative file path (e.g. `cloud/production/20_aks.tf`). Also include region, SKU/tier, version, HA config, node counts. Omit tags and operational metadata.
