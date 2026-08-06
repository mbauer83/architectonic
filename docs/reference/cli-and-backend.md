# CLI & Backend Reference

All commands are installed as console scripts by `uv sync` (defined in `pyproject.toml`).

&nbsp;

## Workspace & setup

| Command | Purpose |
|---|---|
| `arch-init` | Resolve `arch-workspace.yaml`, write `.arch/init-state.yaml` |
| `arch-init --initialize-engagement-repo-if-empty` | Scaffold a configured-but-empty engagement git repo |
| `arch-init --initialize-enterprise-repo-if-empty` | Scaffold a configured-but-empty enterprise git repo |
| `get-plantuml` | Download and verify `plantuml.jar` (beside `pyproject.toml`) from Maven Central |
| `get-diagram-runtime` | The same jar plus a supported Graphviz — for hosts whose system Graphviz is too old |
| `check-diagram-runtime` | Verify Graphviz ≥ 2.49.0 / PlantUML compatibility |

&nbsp;

## Engagement switching

```bash
uv run arch-switch-engagement CLIENT-B                                   # switch active engagement, restart backend
uv run arch-switch-engagement CLIENT-C --url git@github.com:org/c.git    # register a git-backed engagement (clones beside workspace)
uv run arch-switch-engagement CLIENT-D --local ../client-d --create      # scaffold a new local engagement
uv run arch-switch-engagement CLIENT-E --url git@github.com:org/e.git --create   # scaffold + attach origin
```

`--create` scaffolds the standard directory structure (`model/`, `docs/`, `diagram-catalog/`,
`.arch-repo/`), a git repo on the configured branch, an initial commit, and default
frontmatter / attribute-profile / document-type schemata.

&nbsp;

## Backend

```bash
uv run arch-backend --daemon              # serve REST :8000, MCP :8000/mcp/{read,write}; GUI at / if built
uv run arch-backend --status
uv run arch-backend --stop
uv run arch-backend --restart --daemon
```

| Mode | Flag | Effect |
|---|---|---|
| Normal (default) | — | Read/write engagement; enterprise read-only via promotion |
| Admin | `--admin-mode` | Direct enterprise authoring, exclusively through the admin operations surface (`/admin/api/*`); standard authoring tools stay engagement-only even here; GUI shows a banner |
| Read-only | `--read-only` | Every architecture-repository mutation is denied on every interface (REST, MCP, GUI) by the server-side authorization policy — authoring, group and viewpoint writes, promotion, save/submit/discard |

`--daemon` starts a detached session, redirects stdin from `/dev/null`, and writes to
`backend.log_path`. `arch-backend &` also works and detaches stdin when it detects a
background TTY job, but `--daemon` is the preferred operational form.

Every one of these commands is scoped to **this workspace's** backend, identified by the
repositories it serves rather than by the port it occupies. So a start whose preferred port is taken
by another workspace's backend serves on a derived port and says so, `--status` reports such a
neighbour as `port 8000 is serving another workspace (…)` instead of as running, and `--stop` never
signals it. `--port` (like `ARCH_BACKEND_PORT` and `backend.port` in `arch-workspace.yaml`) is a
statement rather than a preference: if that port is taken, the command fails and names the occupant
instead of moving. See
[Several workspaces on one machine](configuration.md#several-workspaces-on-one-machine).

&nbsp;

## Repository maintenance

`arch-repair` has two subcommands. The legacy no-subcommand invocation (the flat
`--repo-root`/`--repair-branch`/`--confirm` form) is a **deprecated alias for
`git-repair`** for one release — it still works, prints a deprecation notice on
stderr, and will be removed once that release ships.

```bash
uv run arch-repair git-repair --repo-root <path> --confirm    # guarded, resumable git repair
uv run arch-repair upgrade --repo-root <path>                  # dry-run report (default; never mutates)
uv run arch-repair upgrade --repo-root <path> --commit         # apply
```

**`arch-repair upgrade`** detects and (with `--commit`) applies persisted-format
migrations — version-aware, self-detecting, idempotent. A repo already on the
current format is a true no-op: no writes, no index rebuild, no
`.arch-repo/config.yaml` change, so it is safe to run unconditionally (the
[Docker Compose deployment](docker-compose.md#operations) runs it before every
backend start).

| Flag | Effect |
|---|---|
| `--repo-root <path>` | Repeatable; one or more repo roots to evaluate/upgrade |
| `--workspace <path>` | Resolve engagement + enterprise roots from `arch-init` state instead (repositories only — never operational targets) |
| `--commit` | Apply findings (default: dry-run report only) |
| `--json` | Emit the stable machine-readable report contract instead of human output |
| `--settings <path>` / `--deployment-root <path>` | Explicit **deployment identity** — additionally discovers the deployment's operational targets (guidance cache, signal stores, the operator-owned settings document) |
| `--guidance-cache` / `--signals-db` / `--assurance-store` | Override one operational path within that deployment identity |
| `--exclude-target <kind>` | Operator-run partial commands only — skip one operational target kind; the report then states deployment readiness is NOT certified. Docker startup never excludes a configured active target |

Each repo root is evaluated/applied independently; findings and applied-step
ids are reported per root plus one aggregate summary for `--workspace` runs.

**Operational targets & deployment identity.** Without `--settings`,
`--deployment-root`, or the `ARCH_SETTINGS_PATH` process selector, the command
touches repositories only (a test workspace can never reach your real guidance
cache or stores). With a deployment identity, the same run also discovers,
preflights, and migrates the deployment's operational targets (settings,
guidance cache, signal stores, the assurance store).

Exit codes: a dry run is always `0` — findings, blockers, and
credential-uninspectable targets are report states, not errors. `--commit`
returns:

| Exit | Meaning |
|---|---|
| `0` | Success |
| `1` | Repository-internal step errors |
| `3` | Unresolved blocking migration (nothing written) |
| `20` | Partial apply — re-run to resume |
| `21` | Infrastructure/credential failure before any commit |

The `--json` report contract: `repos` per repository, plus
`report_schema_version`, `operational_targets`, `deployment_preflight`, and
`outcome`.

For how to run an upgrade safely — target discovery, credentials, backups,
quarantine and blocking findings, resuming a partial apply, the Docker startup
behavior, and worked report examples — see the
[upgrade guide](upgrade-guide.md).

&nbsp;

## Model exchange

`arch-exchange` imports and exports C19C v3.1 model-exchange documents (the Open Group's
ArchiMate 3.x XML interchange format). Import applies the ArchiMate 4 migration table —
layer-specific 3.x types (`BusinessService`, `ApplicationProcess`, …) map to the ArchiMate 4
base type plus a specialization; composition is always preserved as composition, never
downgraded to association even when a relationship type turns out not to be permitted
between the resolved entity types (that case is reported, not silently substituted). Export
inverts the table: a specialized entity/connection exports as its native 3.x concrete type
where one exists, or as a compatible extension property (`archrepo-specialization`) on the
closest native type where it doesn't (e.g. `application-component`'s `module`/`service`/
`endpoint` specializations, which have no 3.x equivalent). Both directions go through the
ordinary `artifact_write` layer — the same validation the GUI/MCP use, never raw file
emission.

```sh
uv run arch-exchange import --source model.xml --repo <path>              # dry-run report (default)
uv run arch-exchange import --source model.xml --repo <path> --commit      # apply
uv run arch-exchange import --source model.xml --repo <path> --commit --schema archimate3_Model.xsd
uv run arch-exchange export --out model.xml --repo <path>                  # every entity in the repo
uv run arch-exchange export --out model.xml --repo <path> --scope <id> <id> # a specific scope
```

**Import** is dry-run by default (`--commit` to write); `--repo` defaults to the workspace's
engagement repo. Re-importing the same document updates previously-imported entities
instead of duplicating them (a repo-local `.arch-repo/exchange-identity.json` sidecar, not a
frontmatter field, tracks the mapping — gitignored, since it is a local operational cache,
not a repository artifact). `--schema` points at a locally-fetched C19C XSD for
schema-validated import; it is a dev/test convenience only — the schema itself is
Open-Group-licensed and, like the ArchiMate 4 specification text, is never committed to
this repository.

**Export** defaults to every entity in the repo; `--scope` restricts it to the given
artifact ids (and every connection between two entities in that scope). Every unmapped or
out-of-scope item on either side is reported by kind and reason — never silently dropped.

&nbsp;

## Guidance import

`arch-import-guidance` fetches or reads a published `create_when`/`never_create_when`
guidance document and imports it into **one deployment-level cache**,
`~/.config/arch-repo/guidance-cache/` — never into a repository, and never split by
engagement/enterprise tier. Guidance is a deployment concern, not per-repo state: one running
instance of this software pulls one guidance source, applied to whichever repos it serves.

```sh
uv run arch-import-guidance                                             # the configured default source
uv run arch-import-guidance --dry-run                                   # validate and report; write nothing
uv run arch-import-guidance --source guidance.yaml                      # a local file instead
uv run arch-import-guidance --source https://example.org/guidance.yaml  # any other HTTPS location
uv run arch-import-guidance --source guidance.yaml --module archimate_4 # import only this module alias
uv run arch-import-guidance --source guidance.yaml --strict             # abort on any unknown key instead of dropping it
```

The source defaults to `guidance.default_source` in `config/settings.yaml` — the published
guidance document — so a deployment serving its own guidance changes that one setting instead of
every invocation. Nothing is fetched until the command runs.

Writes `<alias>.guidance.yaml` (the filtered, matched document) plus a provenance sidecar
`<alias>.guidance.meta.yaml` (source, SHA-256, format version, matched/unmatched counts) per
imported module alias, and — when the document carries a top-level `workspace:` section —
one alias-independent `workspace.guidance.yaml` (with its own sidecar) for the cross-cutting,
module-independent stance. `--strict` is the one to reach for while authoring a document: it
turns every unknown or misplaced key — an entity type filed under the wrong domain included —
into an abort instead of a silent drop. `--allow-http` permits a plain-HTTP source (HTTPS is
required by default). Restart the backend to pick up a newly imported cache. See
[Authoring guidance](../05-extensibility/guidance.md) for the hierarchy, document
format, precedence, and empty-state behavior.

&nbsp;

## Other entry points

| Command | Purpose |
|---|---|
| `arch-mcp-stdio-read` / `arch-mcp-stdio-write` | Architecture MCP servers (stdio bridges) |
| `arch-mcp-stdio-assurance-read` / `arch-mcp-stdio-assurance-write` | Assurance MCP servers |
| `arch-write-cli` | Command-line authoring against the write pipeline |
| `arch-assurance …` | Assurance store/archive management — see [Assurance CLI](../04-assurance/storage-and-confidentiality.md#cli-reference) |
| `tools/assurance/ingest_security_signals.py` | Generate an SBOM, acquire OSV data, and ingest one signal snapshot |

&nbsp;

## Security-signal surfaces

Signals are ingested as snapshots anchored on architecture entities; see
[Security signals](../04-assurance/security-signals.md) for the model. All
endpoints require the assurance store unlocked with co-located signals, and are
exposure-filtered before aggregation.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/assurance/arch-artifacts/{id}/security-snapshots` | POST | Ingest a supplied BOM (+ optional advisories) as a new active snapshot |
| `/api/assurance/arch-artifacts/{id}/security-snapshots` | DELETE | Delete every snapshot for that anchor |
| `/api/assurance/security-snapshots/{snapshot_id}` | DELETE | Delete one snapshot |
| `/api/assurance/arch-artifacts/{id}/security-metrics` | GET | Posture metrics for one anchor, from its active snapshot plus VEX |
| `/api/assurance/arch-artifacts/{id}/security-components` | GET | Components of the anchor's active snapshot |
| `/api/assurance/arch-artifacts/{id}/security-findings` | GET | Vulnerability findings, optionally scoped to one component |
| `/api/assurance/arch-artifacts/{id}/lens` | GET | Assurance findings that concern one architecture artifact |
| `/api/assurance/security-stats` | GET | Snapshot aggregate counts across the store |
| `/api/assurance/vulnerabilities/{identifier}/impact` | GET | Every entity currently affected by one vulnerability |
| `/api/assurance/arch-artifacts/{id}/vex-assessments` | GET/POST | List or record VEX assessments for that anchor |

Status codes worth knowing: `423` the store is locked; `403` signal mutations are
denied by the deployment's capability predicate; `409` a reused `request_id` with a
different payload (nothing was written); `404` on a vulnerability's impact means the
identifier is unknown to the store — distinct from a known vulnerability that
currently affects nothing, which is `200` with an empty list. Every failure carries the
shared error envelope: `{"detail": {"code", "message", "details", "request_id"}}`.

The legacy connector endpoints (`bom/import`, `bom/components`,
`vulnerabilities/import`, `vulnerabilities`) were removed when
signals consolidated on the snapshot model (`GET …/aibom/coverage` remains as a
read-only report). Ingest now has one command behind every
transport, so a write cannot bypass the capability gate or the audit record.

&nbsp;

## Deprecations

**ArchiMate connection "cardinality" → "multiplicity" (this release).** Persisted field
and annotation names were renamed for ArchiMate 4 terminology alignment:
`src_cardinality`/`tgt_cardinality` → `src_multiplicity`/`tgt_multiplicity` (REST/MCP
payloads, generated types), and the diagram frontmatter `diagram_connections[]` opt-in key
`include_cardinality` → `include_multiplicity`. There is no runtime backward-compatibility
code for these names — application code reads only the new names. A diagram authored
before this release whose `diagram_connections[]` entry still uses `include_cardinality`
simply stops rendering that connection's multiplicity annotation (non-destructive; every
other opt-in key on the entry keeps working) until migrated. Migration is via
`arch-repair upgrade` (registered step id `d9-multiplicity-rename`, dry-run by default,
`--commit` to apply) — it rewrites only the `include_cardinality` mapping key in place
(diagrams are `.puml` files with embedded YAML frontmatter for most diagram types,
`.md` for matrix-type diagrams; the step scans both), leaving every other line — including
any uncommitted edit — byte-for-byte untouched. The diagram-type-internal
`cardinality_min`/`cardinality_max` participation config is a separate, unrelated concept
and keeps its name.

**References naming an artifact by a former slug (this release).** Renaming an artifact now
rewrites every file that names it, and the confidential store's architecture references are
retargeted alongside. A repository or assurance store written before that carries references
spelled with titles their artifacts have since dropped. Nothing breaks — identity is the
`PREFIX@epoch.random` stem, so such a reference resolves correctly — which is why use never
repairs it: the cost falls on the reader, for whom the slug is the only interpretable part of
an id. `arch-repair upgrade` respells them: step `d10-stale-slug-references` for repository
content (sidecars, diagram sources, prose citations, and the endpoints inside composite
connection ids), and `assurance-arch-ref-respell` for the store's `arch_refs`. Both key on the
stem, so a reference holding some third, older slug is healed too, and both decline when a stem
has two current spellings (engagement and enterprise can each hold one) rather than guessing.
The store step needs a repository to ask, so a deployment-only run — one with no `--repo-root`
or `--workspace` — migrates nothing there.

&nbsp;

## Troubleshooting

If the GUI hangs on "Loading...", diagnose the transport before assuming a lock:

```bash
uv run arch-backend --status
curl --max-time 5 http://127.0.0.1:8000/api/stats
curl --max-time 5 http://127.0.0.1:5173/api/stats   # if using the Vite dev server
tail -n 100 .arch/backend.log                        # or the configured backend.log_path
```

If `--status` reports `process state: T`, the backend is stopped while still holding the
port. Recover with:

```bash
uv run arch-backend --stop
uv run arch-backend --daemon
```
