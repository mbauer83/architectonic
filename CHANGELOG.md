# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.3.0] — unreleased

**[Full detail → `changelog-assets/0.3.0-detail.md`](changelog-assets/0.3.0-detail.md)**

Several workspaces can now run on one machine without reaching into each other. Every clone ships
`backend.port: 8000`, and a socket answering there was taken for "the backend is already running" —
so an MCP bridge in one checkout proxied a whole session's tool calls, reads and writes alike, into a
different checkout's model, with every response well-formed.

### Fixed

- **A client reaches the backend serving its own workspace, or none.** Endpoints are chosen by what a
  backend reports serving (`GET /api/backend-identity`), not by which port answers. A workspace whose
  preferred port is held by another instance serves on a port derived from its own repository paths
  and says so; a port that was *stated* (`--port`, `ARCH_BACKEND_PORT`, `backend.port`) is never moved
  silently — the command fails and names the occupant.
- **`arch-backend --status` and `--stop` stay inside their workspace.** A neighbour's backend on the
  port this workspace would use was reported as running, and a stop request would have signalled it.
- **`arch-write-cli` refuses to write** to a backend that does not serve the `--repo-root` it was
  given, rather than trusting a recorded port another instance may have taken over.
- **`arch-assurance unlock` authorizes only this workspace's backend.** It posts an authorization to
  the running process, and addressed by port that reached a neighbour's backend — one workspace's
  unlock ceremony granting access to another workspace's confidential store.
- The GUI dev proxy and the browser suite follow `ARCH_BACKEND_PORT`, so developing against a second
  workspace no longer renders the first one's model.

### Added

- `--workspace` / `ARCH_MCP_WORKSPACE` for the MCP bridges, for clients that cannot set a working
  directory. A bridge with no backend of its own exits with the reason instead of attaching to one
  that is not its.
- **`assurance_guidance` teaches the five UCA guidewords the software applies**, and says why the
  Handbook's second is split in two. It taught four while the matrix, the wizard and the attribute
  enum had all moved to five, so an analyst following it under-enumerated. New topic
  `stpa-loss-scenarios` covers the step that had no guidance at all, both Handbook scenario classes;
  every STPA answer now states how its six step numbers map onto the Handbook's four.

### Breaking — what you must change

- **`artifact_bulk_write` answers with one object for the batch, not a list of items.** Read
  `payload["items"]` where you read the list. The batch states `operation_id`, `counts`, `item_count`,
  `failed_count`, `committed` and `refs` — every `_ref` alias against the id it was allocated — once
  instead of repeating them per item. New `return_mode` defaults to `'summary'` (only items with a
  warning or error), with `'full'` for every item in input order and `'ids'` for the alias map and
  counts alone; pass `return_mode='full'` to keep the previous per-item detail. Correlating an alias
  to its id no longer depends on input order surviving the documented auto-sort.

## [0.2.1] — 2026-08-04

**[Full detail → `changelog-assets/0.2.1-detail.md`](changelog-assets/0.2.1-detail.md)**

**Nothing the product serves has changed** — no API, no payload, no behaviour. `0.2.0` was tagged
against a CI run that then went red; this release carries the fixes and closes the gap that let it
happen.

### Fixed

- Three defects in tests and build configuration: a frontend coverage floor that was no longer
  enforced, a dev-proxy test that bound one address and connected to another, and an index-close test
  failed by connections other tests had leaked.

### Quality

- `AGENTS.md` now names every gate CI runs, and a fitness function fails when `ci.yml` gains one it
  does not. Nine were missing — including `npm run test:coverage`, which is the only command that
  applies the frontend coverage thresholds.

## [0.2.0] — 2026-08-03

**[Full detail → `changelog-assets/0.2.0-detail.md`](changelog-assets/0.2.0-detail.md)** ·
**[Route map → `changelog-assets/0.2.0-route-map.md`](changelog-assets/0.2.0-route-map.md)**

The release makes the REST surface something you can generate a client against and trust: every
response body is a declared, closed contract, every operation is addressed by one canonical path, and
one error vocabulary covers REST and MCP alike. That consolidation is what the breaking changes buy —
**there are no aliases and no redirects**, so every consumer moves once, here. Persisted local data is
migrated non-destructively; nothing else is.

### Added — typed bodies and a navigable contract

- **Every response body is a closed, declared model.** No operation publishes an untyped body any
  more: the 69 that answered `additionalProperties: true` behind a shared placeholder are gone, and
  the ledger that tracked them is empty. A body the contract does not describe now fails on the server
  rather than reaching a client that was promised otherwise. The open maps that remain are *named*
  fields whose keys are repository or module data — `attributes`, `properties`, `extra`,
  `display_blocks`, `metadata` — each rostered with its reason.
- **The OpenAPI document is an oracle you can build against.** It is generated from those models, and
  the frontend's own decoders are held against it every commit, so a generated client and the server
  cannot drift apart silently. `operationId` is stable across this release's renames, so a client keyed
  by operation id needs only the new paths.
- **`/docs` is navigable.** Every one of the 166 operations carries exactly one tag — 59 had none, so a
  third of the surface sat under "default" — and the assurance surface subdivides into six sections.
  `/docs/architecture` and `/docs/assurance` render the same document filtered, with
  `/openapi/{section}.json` beside them. The contract itself is not split: one document, one client.
- **Every response carries `X-Request-ID`**, echoed from the request when supplied; every error
  response carries `Cache-Control: no-store`.
- **The document's version is the package version.** It read `0.3.0` against a `0.1.0` package, so a
  client pinning the document version was pinning a number nothing produced.

### Breaking — what you must change

- **79 routes are renamed.** `operationId` is unchanged across the renames, so a generated client keyed
  by operation id needs only the new paths. The route map lists every one with its replacement.
- **Every error body changes shape.** `detail` is an object, not a sentence:
  `{"detail": {"code", "message", "details", "request_id"}}`, with `code` a closed vocabulary.
  **Anything parsing `detail` as a string must change** — including on the assurance surface, which had
  an error vocabulary of its own, so a client branching on `detail.code` fell through on every refusal
  it made.
- **Partial updates are `PATCH`, whole-resource replacements are `PUT`; `POST …/edit` is gone.**
  Deletions return `204` with no body — except a dry run, which returns `200` with its envelope.
- **Four operations split or collapsed** and so cannot appear as renames: `GET /api/ontology` became
  `…/classification` and `…/pairs`; the four `*-complete` endpoints became one method-discriminated
  `…/completeness`; `POST /api/assurance/security-snapshot-delete` became two addresses; the unscoped
  FMEA matrix is gone.
- **An assurance node is created inside its provenance analysis**, and provenance is mandatory.
  Participation is an idempotent relation on `…/participating-nodes/{node_id}`, not a collection post.
- **A concept's specializations are one field.** The scalar `specialization` is gone from every response
  and every write input; `specializations` is the ordered set (ArchiMate §15.2 permits several). Send
  `["x"]` where you sent `"x"`, `[]` to clear; read `specializations[0]` where you read the scalar. The
  on-disk frontmatter key keeps its singular name and its scalar-or-list value, so **no repository
  migration is needed**, and the `?specialization=` selector on `GET /api/entity-schemata/{type}` is a
  different thing and unchanged.
- **`assurance_create_node` requires `analysis_id`**, and MCP execution errors now report the REST
  error vocabulary — one word per failure across both surfaces.
- **`dry_run` defaults to `true` on every write.** The three document routes and
  `DELETE /api/viewpoints/{slug}` defaulted to committing; they now plan. Pass `dry_run: false` (body)
  or `?dry_run=false` (query) to commit, as the other 25 operations always required.
- **Document writes answer 404 for an absent artifact and 400 for a malformed payload**, not 500.
- **`POST /api/identifiers/allocate` no longer accepts `owner_kind`.** It was in the schema, hard-coded
  by every caller, and read by nothing. `diagram_type` and `entity_type` remain required.
- **A rejected viewpoint parameter's `message` no longer carries a retired code word.** Branch on
  `detail.code` and read the parameter from `details.field_errors[].field` (`path` on MCP).
- **`arch-gui-server` is gone.** It raised `ModuleNotFoundError` on any invocation; use `arch-backend`.

### Fixed

Eleven defects, every one reachable in ordinary use and invisible to the gates that existed when it
shipped. Two are worth calling out because they affect deployments rather than the UI:

- **Security-signal ingest refused every anchor unless the server ran from its workspace directory.**
  `POST /api/assurance/arch-artifacts/{id}/security-snapshots` answered "no architecture entity exists"
  for entities that did, in any deployment that configures `ARCH_REPO_ROOT` without a workspace config —
  a mode the shipped container supports. Containers and service-managed installs are affected.
- **A domain card on the Home page opened the last-browsed project** rather than the repository-wide
  list its count was computed over, so the number and the destination disagreed.

Of the remaining nine, the ones most likely to have affected you: a repository-authored viewpoint
could not be applied to anything, a viewpoint with a binding made `GET /api/viewpoints` answer 500 for
everyone, the FMEA matrix rendered blank for any analysis with no dismissals, and every assurance deep
link resolved to an empty page. All nine are listed in the detail file.

### Quality

Every REST operation and every MCP write tool is now exercised over its own transport, against a
disposable repository and a disposable confidential store, and the register that tracked
never-requested operations is empty. That machinery is the reason to trust a release which renames 79
routes — and the eleven defects above are the reason it exists.

## [0.1.0] — 2026-07-29 — first public release
- Typed, git-versioned architecture repository (ArchiMate 4) with GUI, REST, and MCP surfaces
- Two-tier engagement/enterprise model with reviewed promotion (plan-time closure, git-transactional rollback)
- Generated diagram catalog with authored-grouping preservation and manual-layout protection
- Confidential assurance tier (STPA/CAST/GRC/FMEA/GSN) on an encrypted store with tamper-evident history
- Viewpoint query engine with diagram/matrix/table representations

[0.2.1]: https://github.com/mbauer83/architectonic/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mbauer83/architectonic/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mbauer83/architectonic/releases/tag/v0.1.0
