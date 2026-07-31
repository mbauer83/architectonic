# Assurance GUI capability and exposure design

Status: **historical design record** (accepted 2026-06-20, since implemented)

This document records the capability inventory and decisions that preceded the
assurance HTTP and GUI implementation. The design has since been realized. The
inventory's HTTP column is kept truthful by a live test
(`tests/common/test_documentation_claims.py` verifies every named endpoint against
the registered routes); the use-case framing and gap notes reflect the original
design context. For task-oriented documentation of what exists today, see —
[Exploring assurance](../04-assurance/exploring-assurance.md),
[Methods](../04-assurance/methods.md),
[Security signals](../04-assurance/security-signals.md), and
[Assurance MCP tools](../04-assurance/mcp-tools.md). The target architecture
remains hexagonal: HTTP and MCP are adapters over shared application use cases and
policies, not peer implementations of assurance behavior.

## Capability inventory

Legend:

- **App**: reusable application-layer use case exists.
- **MCP R/W**: read/write MCP tool exists.
- **HTTP/GUI**: current implemented surface.
- **Unlock**: `Y` gated, `S` gated only for confidential signal storage, `N`
  callable without the store.
- **TLP**: `Y` filtered, `P` partial/unsafe, `N` absent or not applicable.
- **Audit**: `Y` append-only audit entry, `P` baseline self-audits, `N` absent.
- **Verify**: `Y` is verification, `P` preflight only, `N` no post-write check.

| Capability | App | MCP R | MCP W | HTTP | GUI | Unlock | TLP | Audit | Verify |
|---|---|---|---|---|---|---|---|---|---|
| Store status/reload | — | status | — | status, reload | status/banner | N | N/A | N | N |
| Method guidance | — | guidance | — | — | — | N | N/A | N | N |
| List/read nodes | — | list, read | — | — | — | Y | P | N | N |
| List edges | — | list | — | — | — | Y | N | N | N |
| Store statistics | — | stats | — | — | — | Y | N | N | N |
| Structural verification | verifier | verify | — | — | — | Y | N | N | Y |
| STPA completeness | STPA profile | complete | — | — | — | Y | N | N | Y |
| CAST completeness | CAST profile | complete | — | — | — | Y | N | N | Y |
| GRC completeness | GRC profile | complete | — | — | — | Y | N | N | Y |
| Risk register | — | risk register | — | — | — | Y | N | N | N |
| Coverage dashboard | — | coverage | — | — | — | Y | N | N | P |
| Draft GSN | draft builder | draft GSN | — | — | — | Y | N | N | P |
| Assurance-case completeness | case profile | complete | — | — | — | Y | N | N | Y |
| List BOM components | — | list | — | — | — | S | Y | N | N |
| List vulnerabilities | — | list | — | — | — | S | Y | N | N |
| Security-signal statistics | — | stats | — | — | — | S | N | N | N |
| Scan AI candidates | — | scan | — | — | — | N | N/A | N | N |
| Export AI-BOM | — | export | — | — | — | N | N/A | N | N |
| AI-BOM coverage | — | coverage | — | — | — | S | Y | N | P |
| Create node | — | — | create | — | — | Y | N | Y | N |
| Edit node | — | — | edit | — | — | Y | N | Y | N |
| Delete node | — | — | delete | — | — | Y | N | Y | N |
| Add edge | — | — | add | — | — | Y | N | Y | N |
| Remove edge | — | — | — | — | — | — | — | — | — |
| Seal baseline | — | — | seal | — | — | Y | N | P | N |
| List baselines | archive port only | — | — | — | — | Y | N | N | N |
| Register architecture reference | — | — | register | — | — | Y | N | Y | N |
| Model and bind architecture gap | — | — | task spec only | — | — | Y | N | N | N |
| Promotion preflight | promotion preflight | — | preflight | — | — | Y | P | N | P |
| Ingest security signals | ingest command | — | ingest | security-snapshots | entity page + wizard | S | Y | Y | N |
| Delete signal snapshot | — | — | delete | security-snapshots | — | S | Y | Y | N |
| Component vulnerabilities | signals read | list | — | security-findings | findings view | S | Y | N | N |
| Vulnerability impact | impact use case | impact | — | impact | impact view | S | Y | N | N |
| Reconcile AI-BOM | — | — | reconcile | — | — | N | N/A | N | N |

`P` for node reads means list/read filter node records, but a direct forbidden
read discloses classification and node identity, and the read-node response
returns unfiltered adjacent edges. Withheld counts also disclose classified
cardinality. Aggregate, verification, and dashboard tools operate over the
unfiltered graph.

**Signals superseded (2026-07-21).** The legacy connector rows in this inventory
(`Import BOM`, `Import vulnerabilities`, `Set component anchor`, AI-BOM coverage)
described adapters that called connectors directly and did not consistently gate,
audit, or verify. They were replaced by the signal-snapshot model, in which every
ingest runs through one application command under the signal-mutation capability
gate and lands its audit record in the same transaction. The rows above reflect
the current surfaces; see [Security signals](../04-assurance/security-signals.md).

Ingest IS a GUI capability, reached from the architecture entity it anchors (and
from the supply-chain wizard), consistent with contract 1 above: the architecture
model is the entry point for assurance work. The browser is another adapter over
the same gated command, not a bypass — a CycloneDX document carries its generator
in `metadata.tools`, and the request id is supplied by the form or generated
server-side. The admissible anchor types are served from
`/api/assurance/signal-anchor-types` so the GUI cannot offer an ingest the API
would refuse.

### Required application use cases

Before adding REST mutation or query adapters, extract these application
services behind the existing ports:

1. analysis CRUD, membership assignment, and analysis-scoped browse/detail;
2. exposure-safe node, edge, aggregate, finding, baseline, and search queries;
3. mutation policy plus node CRUD, edge add/remove, and architecture-reference
   registration with audit and post-write verification;
4. baseline list/seal scoped to one analysis;
5. risk register, coverage, method completeness, and GSN draft scoped to one
   analysis rather than the whole store;
6. security-signal reads/writes with the same unlock, classification, audit,
   and verification policy;
7. model-and-bind orchestration; the current tool only returns a cross-server
   task specification and performs no creation or binding;
8. typed GSN argument publication; generic assurance node creation is not a GSN
   authoring API.

The existing verification profiles, GSN draft builder, and promotion preflight
are reusable domain/application functions, but they must receive an
analysis-scoped, exposure-filtered graph view.

## Architecture-grounding contracts

The architecture model is the entry point and navigation spine for assurance.
These contracts applied to all of the assurance HTTP and GUI implementation work:

1. Creating an analysis requires one visible architecture artifact as its
   anchor. The UI starts this flow from entity or diagram detail when possible;
   the assurance landing page uses the same architecture picker.
2. An architecture assurance lens queries by architecture artifact ID and
   returns visible analyses, findings grouped by assurance type, coverage gaps,
   and binding status. A diagram lens aggregates its bound model entities but
   preserves the originating entity ID on every result.
3. Assurance node detail returns visible architecture references and the
   analysis anchor. Navigation to an architecture artifact uses the normal
   architecture detail route; reverse references are computed from the
   assurance store and are never persisted in the architecture repository.
4. Binding status is one of `bound`, `unbound-pending`, `dangling`, or
   `not-applicable`. Gap findings use stable codes for missing analysis anchor,
   unbound node, dangling architecture reference, and assurance content that
   names an unmodelled control/component.
5. Gap badges are derived from analysis-scoped verification/coverage results,
   not independently inferred by Vue components. They appear in architecture
   lenses, assurance browse/detail, diagrams, and method wizards.

`ModelAndBind` is an application use case with assurance-store,
architecture-query, and optional architecture-write ports. It validates the
proposed architecture type, previews the entity, and returns one of:

- `Bound`: create the architecture entity, register the one-way assurance
  reference, and mark the node bound. If assurance binding fails after entity
  creation, return a compensating task and leave the node `unbound-pending`;
  never claim atomicity across the two repositories.
- `TaskRequired`: emit the existing structured architecture-write task when no
  write port is available or separation of duties is requested. The task
  carries the assurance node, analysis anchor, proposed entity, and follow-up
  binding steps without classified narrative.

The current `assurance_model_this` MCP tool is only the second outcome. G4/G5
must move this orchestration into the application layer, with MCP and HTTP as
thin adapters.

## AssuranceExposurePolicy

`AssuranceExposurePolicy` is an application-layer policy. MCP and HTTP adapters
translate its typed outcomes into transport-specific responses. Infrastructure
stores do not decide what may be exposed.

Inputs are the configured TLP ceiling, store state, operation kind, requested
analysis, and optional target classification. The policy produces one of:
`Visible(value, scope)`, `Locked`, `NotFound`, or `ForbiddenWrite`. `scope`
contains the ceiling and `visibility_limited`, which is true whenever the
configured ceiling is below `TLP:RED`; it never reports whether or how many
records were withheld.

Rules:

- A locked confidential store yields HTTP `423 Locked`. MCP returns the stable
  `assurance_store_locked` error envelope. Status and method guidance remain
  callable.
- A direct read of an absent or above-ceiling analysis, node, edge, baseline, or
  finding yields the same HTTP `404` and MCP `not_found` result. It must not
  return the hidden ID, TLP, name, or existence.
- Collection reads omit above-ceiling records and return counts calculated only
  from visible records. `visibility_limited` communicates the configured scope
  without leaking hidden cardinality. An empty list is therefore genuinely
  empty within the declared visible scope.
- An edge is visible only when its analysis and both endpoints are visible.
  Edge topology, IDs, attributes, and counts never survive a hidden endpoint.
- Aggregates, statistics, completeness checks, dashboards, and verification
  findings are recomputed from the visible analysis graph. Findings that
  mention a hidden subject are omitted, and totals are visible-only.
- Search evaluates only an analysis-scoped visible graph and returns no hidden
  hit, snippet, count, facet, or timing label containing classified content.
- HTTP `403 Forbidden` is reserved for explicit writes whose requested TLP is
  above the configured ceiling, or a mutation of a target already established
  as visible but not writable under the mutation policy. Read-time `403` is
  prohibited because it confirms existence.
- Cache headers for assurance content are `Cache-Control: no-store`; telemetry
  contains operation, duration, visible result count, and ceiling only.

This policy replaces MCP-specific `_filter_by_ceiling`, withheld responses, and
adapter-local filtering. Negative contract tests must seed distinguishable
secret names, IDs, topology, snippets, and counts and prove they are absent
from every read surface.

## Direct-query benchmark and search decision

The reproducible benchmark is
`tools/assurance/benchmark_assurance_direct_reads.py`. It creates a temporary encrypted
SQLCipher store with 100,000 nodes across 100 analyses, uses one connection per
reader, and applies analysis and TLP predicates before browse, text search, and
aggregate queries. Eight workers issue 800 requests of each operation. No
plaintext index or persistent benchmark artifact is created.

Result on 2026-06-20:

| Query | Median | p95 | p99 | Max |
|---|---:|---:|---:|---:|
| Browse, 100-row limit | 92.907 ms | 108.542 ms | 125.112 ms | 154.278 ms |
| Direct name/content search, 50-row limit | 3.584 ms | 31.836 ms | 58.415 ms | 77.367 ms |
| Visible counts by node type | 7.410 ms | 10.333 ms | 12.098 ms | 16.142 ms |

The first encrypted query on a new connection includes SQLCipher key setup; a
single warm reader measured search median `0.438 ms` and p95 `7.668 ms`.

Decision: G3 uses direct, parameterized, analysis-scoped SQLCipher queries.
The measured concurrent search p95 is comfortably below an interactive 100 ms
backend budget, so an in-memory full-text index adds lifecycle and
confidentiality risk without demonstrated need. Add
`(analysis_id, node_type, created_at)` and `(analysis_id, status)` indices with
the analysis migration. Re-run this benchmark before introducing an ephemeral
index if dataset scale or the query grammar materially changes.

## Analysis aggregate and migration

`AssuranceAnalysis` is the aggregate root:

```text
analysis_id
name
method              STPA | CAST | GRC
architecture_anchor_id
status              draft | active | completed | archived
tlp
created_at
updated_at
```

Every assurance node has a non-null `analysis_id` foreign key. Edges may connect
nodes only within the same analysis. Baselines have a non-null `analysis_id`
and form that analysis's ordered baseline history. Completeness, stats,
verification, search, browse, GSN drafting, and sealing require an analysis ID.
The architecture anchor is the model element being assessed; additional
node-level architecture references remain valid.

The store port gains analysis CRUD/query operations and analysis filters on
node, edge, reference, stats, and baseline operations. Application services
enforce aggregate invariants; SQL foreign keys and compound checks are the
last line of defence.

Migration is staged because the existing mixed graph cannot be partitioned
reliably without operator intent:

1. Back up the encrypted database and append `MIGRATION_BEGIN`.
2. Add `assurance_analyses`; add nullable `analysis_id` columns and prospective
   indices. Existing nodes appear only through a synthetic
   `migration-required` view and cannot be edited or sealed.
3. A migration command creates explicit analyses and assigns every legacy node.
   It rejects cross-analysis edges and requires an architecture anchor. Each
   creation and assignment appends `CREATE_ANALYSIS` or `ASSIGN_ANALYSIS`.
4. After zero unassigned nodes remain, rebuild node/baseline tables with
   non-null foreign keys, set the new schema version, append
   `MIGRATION_COMPLETE`, and verify the hash chain and graph.

Before completion, rollback restores the encrypted pre-migration backup. After
completion, the down migration appends `MIGRATION_DOWN`, stores an encrypted
analysis/membership export, rebuilds the legacy tables without analysis
columns, and preserves baseline `analysis_id` values where the old schema
already supports them. It is intentionally lossy at runtime and requires an
explicit confirmation; the encrypted export permits a later forward restore.

## GSN classification-gated dual home

The assurance service first produces a typed `GsnDraft` from one visible
analysis. Persistence is selected from the argument's effective TLP, which is
at least the maximum classification of its source material:

- `TLP:AMBER` and `TLP:RED`: remain in the encrypted assurance boundary and are
  rendered as derived previews. No source, rendering, search document, or cache
  is written to the architecture repository.
- `TLP:WHITE` and `TLP:GREEN`: may be explicitly published as an
  architecture-repository `gsn` diagram through the arch-repo-write
  application/tool boundary. Publication is audited in assurance.

Publication creates explicit bindings from diagram claims/strategies/solutions
to their source assurance nodes or evidence and to the analysis architecture
anchor. The assurance store retains publication metadata and architecture
artifact IDs; the architecture repository does not gain back-references to
confidential records. Re-publication updates the same diagram under revision
checking.

The existing cleared exemplar remains an architecture-repository diagram and
is changed with `artifact_edit_diagram`. Generic assurance node CRUD never
creates GSN goals, strategies, assumptions, or solutions.
