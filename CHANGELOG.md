# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.0] — 2026-08-01

### Breaking — REST resource addressing and response contracts

Identity of the resource an HTTP operation addresses now belongs in the path; filters stay in the
query. **There are no aliases and no redirects** — every consumer moves in this release. Persisted
local data is migrated non-destructively; nothing else is.

**[Complete route map → `changelog-assets/0.2.0-route-map.md`](changelog-assets/0.2.0-route-map.md)**
(79 retirements with their replacements). `operationId` is unchanged across the renames, so a
generated client keyed by operation id needs only the new paths.

Why the surface is shaped this way is in the ADRs, not here: *Resource Addressing: Identity in the
Path, Filters in the Query*, *Response Contracts Are Owned by the Server and Generated Outward*, and
*The Assurance Analysis Aggregate: Filing, Provenance and Participation Are Three Relations*.

#### Errors — every body changes shape

- **One typed envelope everywhere.** `detail` is an object, not a sentence:
  `{"detail": {"code", "message", "details", "request_id"}}`. `code` is a closed vocabulary,
  `details` is a per-code payload. **Anything parsing `detail` as a string must change.** The
  assurance surface included: it answered `{"error": "...", ...}` with a vocabulary of its own, so a
  client branching on `detail.code` fell through on every refusal it made.
- **A refused deletion is an error, not a `200` carrying `ok: false`.**
- **Three assurance statuses change.** Deleting an analysis that authored nodes is
  `409 analysis_not_empty`; filing under a group that does not exist is `404`; a rejected field value
  is `422`. All three were `400`.
- **A failed signal ingest, an unknown vulnerability and an absent snapshot answer the envelope**
  rather than a body carrying a `status` word. The status codes are unchanged.
- **An identifier that collides with a literal collection segment is refused** with `400` — a
  viewpoint named `pins` or `criteria-catalog` could be written and never read back.

#### Methods and statuses

- **Partial updates are `PATCH`; whole-resource replacements are `PUT`.** `POST …/edit` is gone.
- **Deletions return `204` with no body** — except a dry run, which returns `200` with its envelope.
- **Recording an FMEA factor is `POST`**, at
  `/api/assurance/nodes/{node_id}/factor-assessments`: it appends a revision, and `PUT` promised an
  idempotence the surface never had. `node_id` leaves the body.

#### Routes that split or collapse (not in the route map, which lists renames)

- **`GET /api/ontology` becomes two.** It chose its shape by whether `target_type` was supplied, so
  no single schema could describe it. Use `GET /api/ontology/classification?source_type=` for what a
  type may connect to, and `GET /api/ontology/pairs?source_type=&target_type=` for what is permitted
  between an ordered pair. Naming a document or diagram reference as an endpoint now answers `422`.
- **The four `*-complete` endpoints collapse into one.**
  `GET /api/assurance/analyses/{id}/completeness` returns a method-discriminated response; `method`
  names which report it answered and the argument case travels under `case`. A method with no
  completeness projection returns `409 analysis_method_mismatch`.
- **`POST /api/assurance/security-snapshot-delete` is gone**, and with it the body that chose between
  deleting one snapshot and all of an anchor's. The scope is the address:
  `DELETE /api/assurance/security-snapshots/{snapshot_id}` or
  `DELETE /api/assurance/arch-artifacts/{arch_artifact_id}/security-snapshots`.
- **The unscoped FMEA matrix is gone.** `GET /api/assurance/fmea` with no analysis returned every
  failure mode in the store; the matrix is a projection of one analysis.

#### The assurance analysis aggregate

- **`POST /api/assurance/nodes` is gone.** A node is created inside its provenance analysis, at
  `POST /api/assurance/analyses/{analysis_id}/nodes`, and provenance is mandatory. `analysis_id`
  leaves the node edit contract; `PUT /api/assurance/nodes/{node_id}/provenance` is the only route
  that may set it, and only for an unattributed node — re-asserting the same analysis is `204`,
  asserting a different one is `409 provenance_immutable`.
- **Participation is a relation, not a collection post.**
  `PUT`/`DELETE /api/assurance/analyses/{id}/participating-nodes/{node_id}` are idempotent and answer
  `204`; the node is in the path. A node may not participate in the analysis that authored it —
  `409 invalid_participation`.
- **Deleting a node another analysis references is refused** with `409 entity_in_use`, and the details
  name the referencing analyses. Remove the participation relations first.
- **Deleting an analysis ends the participation it held, and nothing else** — the nodes it authored
  survive with their provenance intact.

#### MCP

- **`assurance_create_node` requires `analysis_id`**, `assurance_edit_node` no longer accepts it, and
  `assurance_assign_provenance` is the repair tool for an unattributed node.
- **Execution errors report the REST vocabulary.** The shape is unchanged — JSON-RPC has no HTTP
  envelope, so a failure still arrives in band as `{"error": {code, path, message}}` — but the `code`
  is now the same word REST uses. `execution-timeout` and `derivation-limit` become
  `traversal_time_budget_exceeded`, `binding-cardinality-violation` becomes
  `binding_cardinality_violation`, and `missing-parameter` / `unknown-parameter` /
  `parameter-type-mismatch` become `validation_error` with the finer distinction in the message.
  An agent reading both surfaces saw two names for one failure.

#### CLI

- **`arch-gui-server` is gone.** It named `src.infrastructure.gui.gui_server`, a module this release
  renamed, so the command raised `ModuleNotFoundError` on any invocation. Nothing referenced it and
  `arch-backend` is the documented way to run the server, so it was removed rather than repointed.

#### Fixed

Each of these was reachable in ordinary use and invisible to every gate; the browser suite is what
found them.

- **A repository-authored viewpoint could not be applied to anything.** The write path built its
  verifier from the process catalogs, whose viewpoint catalogue is the module-shipped starter
  library and reads no repository — so a diagram or matrix naming a definition you had just saved
  was refused with `E180 Unknown viewpoint slug`, permanently rather than until a restart.
- **A viewpoint with a binding made `GET /api/viewpoints` answer 500 for everyone.** The response
  contract declared `select` as `entity`/`connection`; the domain and the write path use
  `entities`/`connections`. One saved definition took the whole catalogue down with it.
- **The FMEA matrix rendered blank for any analysis with no dismissals.** `dismissal` was served as
  `{}` while the published contract declares both of its fields present, so the client's decode
  threw before a single row was drawn.
- **Three assurance links pointed at retired addresses** — the node list and its rows to
  `/assurance/node/{id}`, "Explore graph" to `/assurance/graph?node_id=`, and the FMEA wizard to the
  flat `/assurance/fmea` — and the standalone node page read the pre-rename `id` route parameter, so
  every assurance deep link resolved to an empty page.
- **An unserved address renders a not-found page.** There was no catch-all route, so a retired
  address, an old bookmark or a stale link rendered the chrome and an empty `<main>`.
- **`/api/diagrams/preview` answers 400 for a selection the diagram type cannot draw**, naming
  `diagram_entities`, instead of a 500 whose body deliberately carries no diagnostic.
- **A `?param.` value on a shared link is honoured.** For a definition whose parameters are all
  optional or defaulted the gate discarded them and the address-rewriting surfaces then erased them
  from the URL, so such a link could not even be re-shared. A value the parameter's type cannot
  represent now reaches the server and is refused, rather than being silently read as `false`.
- **The preview's derived-entity checklist honours the server.** The scope root can no longer be
  unchecked — the engine will not exclude it — and a server-side exclusion renders as excluded.
- **A witness chain that cannot be read says so** instead of showing "Loading witness chain…"
  for as long as the dialog stays open.

#### Additive

- **Every response carries `X-Request-ID`**, echoed from the request when supplied; every error
  response carries `Cache-Control: no-store`.
- **The OpenAPI document's version is the package version.** It previously read `0.3.0` against a
  `0.1.0` package, so a client pinning the document version was pinning a number nothing produced.

## [0.1.0] — 2026-07-29 — first public release
- Typed, git-versioned architecture repository (ArchiMate 4) with GUI, REST, and MCP surfaces
- Two-tier engagement/enterprise model with reviewed promotion (plan-time closure, git-transactional rollback)
- Generated diagram catalog with authored-grouping preservation and manual-layout protection
- Confidential assurance tier (STPA/CAST/GRC/FMEA/GSN) on an encrypted store with tamper-evident history
- Viewpoint query engine with diagram/matrix/table representations

[Unreleased]: https://github.com/mbauer83/architectonic/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/mbauer83/architectonic/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mbauer83/architectonic/releases/tag/v0.1.0
