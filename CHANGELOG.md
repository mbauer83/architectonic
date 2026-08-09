# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

**Somewhere to think before anything is typed.** The typed model asks a contributor to name an
element type before they have decided anything, and that question is the wall this removes.

### Added

- **A scratchpad tier.** Notes and links on a canvas, with no ontology involved: a note needs only a
  title. The canvas saves itself at most once a second after editing settles, so the endpoint sees a
  save and never a drag, and undo holds whole documents so every kind of edit is reversible.
- **Binding.** Right-click the canvas → *Add existing element…* puts an entity the model already has
  onto the canvas as a bound note, at the point you clicked, scoped to the types that frame permits.
  It takes its type from the entity, so a lift cannot mint a duplicate of it.
- **Narrowing, one level at a time**, down the meta-ontology's own classification levels — which
  `classification_levels` now lets a module declare rather than every consumer hard-code. A note
  wears its domain as a colour and its type as that type's glyph.
- **Two-tier link verification, served with each link.** A refusal at the level relationships are
  keyed on (**E126**) blocks; a narrowing by a specialization (**W128/W129**) warns. Both fall out of
  the ontology's declaration rather than a rule in the verifier, and a refusal leads with *Reverse
  the link* when the reverse is the permitted one.
- **Lift, preflighted.** A selection becomes ordinary verified model content through the same write
  path as any other authoring. The dialog reports what would be created, what is refused and why,
  what is already in the model, and which links reach outside the selection. A refusal blocks the
  whole lift, because the write is one transaction. A target project is chosen **per frame** and
  created if it is new; one declaring a different meta-ontology is refused rather than coerced.
- **Documents as a destination**, with the reference rule: a link touching a document becomes a
  one-way reference *from the document to the model*, recorded on the document, whichever way it was
  drawn. `artifact_bulk_write` gained `create_document` so that stays inside one transaction.
- **An optional view of what was lifted**, with each of the scratchpad's groups as a labelled box.
  Frames map to nothing — an area is a region of the workspace, not an element of a picture.
- **Focus mode**, and a canvas that works without a pointer: the notes layer is a real multi-select
  listbox, every gesture has a key, and what is selected is announced rather than only drawn.
- **Six MCP tools and six REST operations**, held equal by a parity test — the scratchpad is the
  lowest-barrier surface, so a human-only version would make the one place newcomers start the one
  place an agent cannot help.

### Fixed

- **An ArchiMate box is no longer as wide as its widest unwrapped label.** All seven `archimate-*`
  types emitted no `skinparam wrapWidth`; on one diagram, 2545x798 became 1671x952. All 32 committed
  ArchiMate diagrams were re-rendered and every one still lays out.

## [0.3.1] — 2026-08-08

**[Full detail → `changelog-assets/0.3.1-detail.md`](changelog-assets/0.3.1-detail.md)**

**Nothing the product serves changed shape.** A cold verification no longer takes the backend with it.

### Fixed

- **A whole-repository verify no longer blocks every other request for its duration.** It held the
  workspace gate for the whole pass and ran on the event loop; it now reads under exclusivity (192 ms
  for 880 files) and evaluates outside it. Identity p95 during a pass went from 5.9x idle to 1.5x.
- **Verification could deadlock a promote or a cascade-delete**, which verify while holding the
  non-reentrant write gate. A full pass reached from the incremental path also swept the tree twice,
  recording files as verified at contents they never held. A waiting writer was unreachable under
  sustained reads, and lock ownership was mirrored in a thread-local that offloading invalidates.
- **A second backend on one machine served its MCP tools from the *first* workspace's repository**,
  while reporting its own roots on `/api/backend-identity`: the MCP layer resolved its default
  repository from where the code lives, not from what the backend serves, so reads, writes and
  deletes could land in a neighbour's model. Only multi-workspace deployments were affected.
- **A diagram no longer draws a domain box for a domain an authored grouping emptied**, which a
  grouping spanning several domains leaves behind for each domain it draws from.

### Changed

- **`artifact_verify` refuses an unconfirmed full pass** in milliseconds, naming which of four
  conditions requires it and how many files it would read; pass `confirm_full_pass=true` or set
  `ARCH_MODEL_VERIFY_MODE=full`. A concurrent pass is refused, not queued; a cancelled one leaves no
  state. It **verifies one file at a time now** — the pool cost 4x the wall clock and 4.4x the CPU
  for the same files; `ARCH_VERIFY_WORKERS` opts back in.

## [0.3.0] — 2026-08-08

**[Full detail → `changelog-assets/0.3.0-detail.md`](changelog-assets/0.3.0-detail.md)**

Several workspaces can now run on one machine without reaching into each other. An entity can be
drawn more than once on a diagram and connected differently in each place. And `arch-repair upgrade`
repairs references that name an artifact by a name it no longer has.

### Added

- **A diagram can draw an entity more than once and connect each drawing differently.** Each drawing
  gets its own row in Included Entities, with its own connections and its own related-entity list. A
  relation may be drawn once per pair of drawings, so a cluster duplicated to keep arrows untangled
  reads as a complete unit in each copy. Existing diagrams are unaffected.
- **Diagrams can draw labelled boxes the model does not hold, and the boxes style themselves.**
  `authored_groupings` reaches `artifact_create_diagram`, `artifact_edit_diagram`, the REST write
  routes and a Groupings panel in the GUI; the key rendered before but was reachable only by
  hand-editing the file. The look is derived from the members. A member may name an occurrence id, so
  an entity drawn twice sits in a different box each time, and boxes nest.
- **`arch-repair upgrade` respells references that name an artifact by a former slug** — in
  repository files and in the confidential store's architecture references. Dry-run by default,
  `--commit` to apply; both steps decline where a stem has two current spellings rather than guessing.
- `--workspace` / `ARCH_MCP_WORKSPACE` for the MCP bridges, for clients that cannot set a working
  directory. A bridge with no backend of its own exits with the reason instead of attaching to one
  that is not its.
- **A goal realized through the goals it aggregates is no longer a gap.** `motivation-coverage` now
  declares the whole-part edge it composes over (`rollup`), so an aggregate carries its constituents'
  obligations instead of one of its own, at every level.
- **`assurance_guidance` teaches the five UCA guidewords the software applies**, and says why the
  Handbook's second is split in two. New topic `stpa-loss-scenarios` covers the step that had no
  guidance at all. Every STPA answer states how its six step numbers map onto the Handbook's four.

### Fixed

- **`arch-backend --daemon --port` could fail to start**, because the daemon matched its own launcher
  as an instance already serving that port. Startup now waits for the process to begin serving rather
  than for a fixed number of seconds, so a large repository's first index build no longer times out.
- **A preview now shows the diagram the write will save.** Authored groupings reached both writes and
  never the preview, and the two rendered different input, so a box was invisible until saved.
- **Six further fixes**, each with its own section in the detail file: connection ids minted from a
  hyphen-free alphabet, so a composite id no longer splits in the wrong place; AND/OR junctions no
  longer a dead end for tracing (`RJ3`); a junction refused a relationship its participants could not
  hold (**E128**/**E129**); a diagram naming an artifact by a former slug reported
  (**W305**/**W306**); a batched rename rewriting its referring files, as a single-entity rename
  always did; and `entity_ids` on `artifact_edit_diagram` setting what the diagram draws, as it
  always has on create.
- **A rename now reaches the confidential assurance store, when it is unlocked.** A registered
  follower retargets the stored references, matching on the stem so an older spelling heals too. A
  locked or unconfigured store means no failure.
- **A batch item carrying a field its operation does not accept is refused, not performed
  differently.** An item passing `mode: "remove"` had that field ignored, ran as an update, and
  reported `wrote: true` for a removal that never happened. Every op declares its accepted fields.
- **"Browse" no longer carries a diagram type into the entity browser as a filter.** Arriving from a
  diagram page set the entity-type filter to a value no entity matches, showing an empty list.
- **A grouping's realization now reaches its members, as a visible inference** carrying
  `diagnostic_code: potential_realization` — a relationship of a whole only potentially holds of each
  part (`PDR12`). An empty grouping still realizes nothing.
- **A client reaches the backend serving its own workspace, or none.** Endpoints are chosen by what a
  backend reports serving (`GET /api/backend-identity`), not by which port answers.
- **`arch-write-cli` refuses to write** to a backend that does not serve the `--repo-root` it was
  given, rather than trusting a recorded port another instance may have taken over.
- **`arch-assurance unlock` authorizes only this workspace's backend.** Addressed by port, it could
  reach a neighbour's — one workspace's unlock ceremony granting access to another's store.
- The GUI dev proxy and the browser suite follow `ARCH_BACKEND_PORT`, so developing against a second
  workspace no longer renders the first one's model.

### Security

- **Five advisories closed before release** — `cryptography` to 50.0.0, `nanoid` to 3.3.18,
  `dompurify` to 3.4.13, and `js-yaml` to 3.15.1 and 4.3.1. Two arrived as dependency PRs; the
  other three are transitive and had none, so `js-yaml` needed an override scoped to
  `@redocly/openapi-core` rather than a global pin, which would have broken `nyc`'s 3.x
  requirement. Both audit surfaces report clean, and the product's own supply-chain ingest was
  re-run against live OSV data for the backend and the GUI — 114 and 384 components, no findings.

### Breaking — what you must change

- **`artifact_bulk_write` answers with one object for the batch, not a list of items.** Read
  `payload["items"]` where you read the list. New `return_mode` defaults to `'summary'` (only items
  with a warning or error); pass `return_mode='full'` to keep the previous per-item detail. The batch
  states `operation_id`, `counts`, `item_count`, `failed_count`, `committed` and `refs` once instead
  of repeating them per item, so correlating an alias to its id no longer depends on input order.

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

[0.3.1]: https://github.com/mbauer83/architectonic/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/mbauer83/architectonic/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mbauer83/architectonic/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mbauer83/architectonic/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mbauer83/architectonic/releases/tag/v0.1.0
