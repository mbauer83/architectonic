# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Breaking — REST resource addressing (0.2.0)

Identity of the resource an HTTP operation addresses now belongs in the path; filters stay in the
query. There are **no aliases and no redirects**: this is a local-first product first released on
2026-07-29, so the only migration obligation is persisted local data, and that is migrated
non-destructively. Every consumer moves in this release.

The rule, and why it is enforced by an executable manifest rather than a convention, is recorded in
ADR *Resource Addressing: Identity in the Path, Filters in the Query*. Response and error contracts
change with it — see ADR *Response Contracts Are Owned by the Server and Generated Outward* — and
the assurance analysis aggregate is reshaped in ADR *The Assurance Analysis Aggregate: Filing,
Provenance and Participation Are Three Relations*.

#### What else changes for a consumer

- **Every error body is the same typed envelope.** `detail` is an object, not a sentence:
  `{"detail": {"code", "message", "details", "request_id"}}`. `code` is a closed vocabulary and
  `details` is a per-code payload. Anything parsing `detail` as a string must change.
- **Every response carries `X-Request-ID`**, echoed from the request when supplied.
- **Every error response carries `Cache-Control: no-store`.**
- **`POST /api/assurance/nodes` is gone.** A node is created inside its provenance analysis, at
  `POST /api/assurance/analyses/{analysis_id}/nodes`, and provenance is mandatory — it was an
  optional body field, which is how 26 nodes came to sit in the store with no author recorded.
  `analysis_id` leaves the node edit contract; `PUT /api/assurance/nodes/{node_id}/provenance` is
  the only route that may set it, and only for an unattributed node. Re-asserting the same analysis
  is idempotent (`204`); asserting a different one returns `409 provenance_immutable`.
- **Participation moves to `participating-nodes` and becomes a relation, not a collection post.**
  `PUT`/`DELETE /api/assurance/analyses/{id}/participating-nodes/{node_id}` are idempotent and
  answer `204`; the node is the path, not a body field. A node may not participate in the analysis
  that authored it — that returns `409 invalid_participation` and writes nothing, rather than being
  deduplicated away.
- **The MCP write surface changes with it.** `assurance_create_node` requires `analysis_id`;
  `assurance_edit_node` no longer accepts it; `assurance_assign_provenance` is the new repair tool.
  Leaving them alone would have left an unguarded route around the invariant.
- **The unscoped FMEA matrix is gone.** `GET /api/assurance/fmea` with no analysis returned every
  failure mode in the store; the matrix is now a projection of one analysis. A method-filtered
  analysis picker replaces it in the GUI.
- **The four `*-complete` endpoints collapse into one.** `GET /api/assurance/analyses/{id}/completeness`
  returns a method-discriminated response — `method` names which report it answered, and the
  argument case's completeness (formerly `gsn/completeness`) travels with it under `case`. The
  analysis decides, not the URL: the old routes took the analysis as an *optional* query parameter,
  so a CAST report could be asked of an STPA analysis and come back empty, reading like a pass.
  A method with no completeness projection — FMEA, whose projection is its matrix — returns
  `409 analysis_method_mismatch`.
- **Recording an FMEA factor is a `POST`, not a `PUT`.** `POST /api/assurance/nodes/{node_id}/factor-assessments`
  appends a revision; `PUT` promised an idempotence the surface never had. `node_id` leaves the
  body — the node's own provenance decides which analysis owns the judgement.
- **The FMEA matrix requires its analysis, and the GUI no longer offers an unscoped one.** With two
  FMEAs the global matrix drew both analyses' rows in one grid, which is not a ranking of either.
  The page shows a method-filtered analysis picker until one is chosen.
- **The OpenAPI document's version is the package version.** It previously read `0.3.0` against a
  `0.1.0` package.
- **`operationId` is `{tag}_{verb}_{resource}`** and is stable across these renames, so generated
  clients keyed by operation id are unaffected by the path changes themselves.
- **Partial updates are `PATCH`; whole-resource replacements are `PUT`.** `POST …/edit` is gone.
- **Deletions return `204` with no body**, except a dry run, which returns `200` with its envelope.
- **`POST /api/assurance/security-snapshot-delete` is gone**, and with it the body that chose
  between deleting one snapshot and deleting every snapshot of an anchor. The scope is the address:
  `DELETE /api/assurance/security-snapshots/{snapshot_id}` or
  `DELETE /api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots`.
- **A failed signal ingest, an unknown vulnerability and an absent snapshot now answer the error
  envelope**, not a `200`/`404` body carrying a `status` word. The status codes are unchanged
  (`409` on a reused request id, `422` on a rejected BOM, `404` on an unknown identifier); the body
  is `{"detail": {...}}` in every case.
- **A refused deletion is an error, not a success saying `ok: false`.** Deleting a viewpoint still
  pinned by a diagram or matrix answers `409 viewpoint_referenced`, whose `details` carry the
  referencing artifact ids and kinds; an unknown slug answers `404`, and an enterprise or module
  definition this repository may not touch answers `403`.
- **A security component is addressable by its own id.** `GET /api/assurance/security-components/{component_id}`
  answers for one component, keyed on the internal `SCM@…` id. Its PURL, CPE and BOM reference stay
  on the row as data and remain usable as collection filters
  (`…/security-components?purl=`) — they identify a *package* in vocabularies other standards own,
  their syntax carries `/`, `?` and `#` by design, and one package arrives under different ones from
  different feeds. A caller holding only a PURL resolves it through the collection first.
- **Deleting an analysis ends the participation it held, and nothing else.** The participation rows
  naming that analysis go with it, in one store-level unit of work, in all four backends — they had
  no foreign key to analyses, so an analysis that only *borrowed* nodes left one orphan row per
  borrowed node. The nodes and their provenance are untouched. An analysis that *authored* nodes
  still answers `409 analysis_not_empty`, and the refusal no longer suggests detaching them:
  provenance is immutable, so the only remedies are to delete them explicitly or leave the analysis
  in place.
- **An identifier that collides with a literal collection segment is refused.** A viewpoint named
  `pins` or `criteria-catalog` could be written and never read back, because those URLs address the
  collection's own subresources — creating or deleting at such a slug now returns `400`.

#### Complete route mapping

| Retired | Canonical |
|---|---|
| `DELETE /api/assurance/analyses/{analysis_id}/members/{node_id}` | `DELETE /api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}` |
| `DELETE /api/document/{artifact_id}` | `DELETE /api/documents/{artifact_id}` |
| `DELETE /api/group` | `DELETE /api/groups/{kind}/{slug}` |
| `GET /api/assurance/analyses/{analysis_id}/members` | `GET /api/assurance/analyses/{analysis_id}/participating-nodes` |
| `GET /api/assurance/arch-lens/{arch_artifact_id}` | `GET /api/assurance/arch-artifacts/{arch_artifact_id}/lens` |
| `GET /api/assurance/cast-complete` | `GET /api/assurance/analyses/{analysis_id}/completeness` |
| `GET /api/assurance/fmea` | `GET /api/assurance/analyses/{analysis_id}/matrix` |
| `GET /api/assurance/grc-complete` | `GET /api/assurance/analyses/{analysis_id}/completeness` |
| `GET /api/assurance/gsn/completeness` | `GET /api/assurance/analyses/{analysis_id}/completeness` |
| `GET /api/assurance/gsn/draft` | `GET /api/assurance/analyses/{analysis_id}/gsn/draft` |
| `GET /api/assurance/gsn/rendered` | `GET /api/assurance/analyses/{analysis_id}/gsn/rendered` |
| `GET /api/assurance/guidance` | `GET /api/assurance/guidance/{topic}` |
| `GET /api/assurance/neighbors` | `GET /api/assurance/nodes/{node_id}/neighbors` |
| `GET /api/assurance/security-components` | `GET /api/assurance/arch-artifacts/{arch_artifact_id}/security-components` |
| `GET /api/assurance/security-findings` | `GET /api/assurance/arch-artifacts/{arch_artifact_id}/security-findings` |
| `GET /api/assurance/security-metrics` | `GET /api/assurance/arch-artifacts/{arch_artifact_id}/security-metrics` |
| `GET /api/assurance/stpa-complete` | `GET /api/assurance/analyses/{analysis_id}/completeness` |
| `GET /api/assurance/vex` | `GET /api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments` |
| `GET /api/assurance/vulnerability-impact` | `GET /api/assurance/vulnerabilities/{identifier}/impact` |
| `GET /api/diagram` | `GET /api/diagrams/{artifact_id}` |
| `GET /api/diagram-connections` | `GET /api/diagrams/{artifact_id}/connections` |
| `GET /api/diagram-context` | `GET /api/diagrams/{artifact_id}/context` |
| `GET /api/diagram-download` | `GET /api/diagrams/{artifact_id}/download` |
| `GET /api/diagram-entities` | `GET /api/diagrams/{artifact_id}/entities` |
| `GET /api/diagram-image/{filename}` | `GET /api/diagram-images/{filename}` |
| `GET /api/diagram-svg` | `GET /api/diagrams/{artifact_id}/svg` |
| `GET /api/diagram-types/datatype/type-usages` | `GET /api/diagram-types/datatype/types/{type_id}/usages` |
| `GET /api/diagram-types/{name}/connection-types` | `GET /api/diagram-types/{diagram_type}/connection-types` |
| `GET /api/diagram-types/{name}/entity-types` | `GET /api/diagram-types/{diagram_type}/entity-types` |
| `GET /api/document` | `GET /api/documents/{artifact_id}` |
| `GET /api/entity` | `GET /api/entities/{artifact_id}` |
| `GET /api/entity-context` | `GET /api/entities/{artifact_id}/context` |
| `GET /api/entity-display-item` | `GET /api/entities/{artifact_id}/display-item` |
| `GET /api/entity-schemata` | `GET /api/entity-schemata/{artifact_type}` |
| `GET /api/matrix-config` | `GET /api/matrices/{artifact_id}/config` |
| `GET /api/neighbors` | `GET /api/entities/{artifact_id}/neighbors` |
| `PATCH /api/group` | `PATCH /api/groups/{kind}/{slug}` |
| `POST /admin/api/connection` | `POST /admin/api/connections` |
| `POST /admin/api/connection/remove` | `DELETE /admin/api/connections/{connection_id}` |
| `POST /admin/api/diagram` | `POST /admin/api/diagrams` |
| `POST /admin/api/diagram/remove` | `DELETE /admin/api/diagrams/{artifact_id}` |
| `POST /admin/api/entity` | `POST /admin/api/entities` |
| `POST /admin/api/entity/edit` | `PATCH /admin/api/entities/{artifact_id}` |
| `POST /admin/api/entity/remove` | `DELETE /admin/api/entities/{artifact_id}` |
| `POST /api/assurance/analyses/{analysis_id}/members` | `PUT /api/assurance/analyses/{analysis_id}/participating-nodes/{node_id}` |
| `POST /api/assurance/baselines/seal` | `POST /api/assurance/baselines` |
| `POST /api/assurance/gsn/publications` | `POST /api/assurance/analyses/{analysis_id}/gsn/publications` |
| `POST /api/assurance/nodes` | `POST /api/assurance/analyses/{analysis_id}/nodes` |
| `POST /api/assurance/security-ingest` | `POST /api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots` |
| `POST /api/assurance/security-snapshot-delete` | `DELETE /api/assurance/security-snapshots/{snapshot_id}` |
| `POST /api/assurance/vex` | `POST /api/assurance/arch-artifacts/{arch_artifact_id}/vex-assessments` |
| `POST /api/cleanup-broken-refs` | `POST /api/connections/cleanup-broken-refs` |
| `POST /api/connection` | `POST /api/connections` |
| `POST /api/connection/associate` | `PATCH /api/connections/{connection_id}/associated-entities` |
| `POST /api/connection/edit` | `PATCH /api/connections/{connection_id}` |
| `POST /api/connection/remove` | `DELETE /api/connections/{connection_id}` |
| `POST /api/diagram` | `POST /api/diagrams` |
| `POST /api/diagram/edit` | `PUT /api/diagrams/{artifact_id}` |
| `POST /api/diagram/entity-metadata` | `PATCH /api/diagrams/{artifact_id}/entities/{classifier_id}/metadata` |
| `POST /api/diagram/preview` | `POST /api/diagrams/preview` |
| `POST /api/diagram/remove` | `DELETE /api/diagrams/{artifact_id}` |
| `POST /api/diagram/sync` | `POST /api/diagrams/{artifact_id}/sync` |
| `POST /api/document` | `POST /api/documents` |
| `POST /api/entity` | `POST /api/entities` |
| `POST /api/entity/edit` | `PATCH /api/entities/{artifact_id}` |
| `POST /api/entity/remove` | `DELETE /api/entities/{artifact_id}` |
| `POST /api/group` | `POST /api/groups` |
| `POST /api/group/archive` | `POST /api/groups/{kind}/{slug}/archive` |
| `POST /api/group/unarchive` | `POST /api/groups/{kind}/{slug}/unarchive` |
| `POST /api/matrix` | `POST /api/matrices` |
| `POST /api/matrix/edit` | `PUT /api/matrices/{artifact_id}` |
| `POST /api/matrix/preview` | `POST /api/matrices/preview` |
| `POST /api/viewpoints/edit` | `PUT /api/viewpoints/{slug}` |
| `POST /api/viewpoints/remove` | `DELETE /api/viewpoints/{slug}` |
| `PUT /api/assurance/fmea/factor` | `POST /api/assurance/nodes/{node_id}/factor-assessments` |
| `PUT /api/diagram/edge-label` | `PUT /api/diagrams/{artifact_id}/edges/{edge_key}/label` |
| `PUT /api/document/{artifact_id}` | `PATCH /api/documents/{artifact_id}` |
| `PUT /api/group` | `POST /api/groups/{kind}/{slug}/rename` |


## [0.1.0] — 2026-07-29 — first public release
- Typed, git-versioned architecture repository (ArchiMate 4) with GUI, REST, and MCP surfaces
- Two-tier engagement/enterprise model with reviewed promotion (plan-time closure, git-transactional rollback)
- Generated diagram catalog with authored-grouping preservation and manual-layout protection
- Confidential assurance tier (STPA/CAST/GRC/FMEA/GSN) on an encrypted store with tamper-evident history
- Viewpoint query engine with diagram/matrix/table representations

[Unreleased]: https://github.com/mbauer83/architectonic/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mbauer83/architectonic/releases/tag/v0.1.0
