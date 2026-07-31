# Configuration Reference

Two files configure a workspace: `arch-workspace.yaml` declares the repositories;
`config/settings.yaml` configures the backend. Per-repository schemata live in each repo's
`.arch-repo/` directory.

&nbsp;

## `arch-workspace.yaml` — repositories

Single active engagement:

```yaml
engagement:
  local: engagements/ENG-ARCH-REPO/architecture-repository
  # or git: { url: "https://...", branch: main, path: .arch/repos/engagement }

enterprise:
  local: enterprise-repository
  # or git: { url: "https://...", branch: main, path: .arch/repos/enterprise }
```

Multiple engagements with an active selector:

```yaml
engagements:
  active: ENG-ARCH-REPO
  available:
    ENG-ARCH-REPO:
      local: engagements/ENG-ARCH-REPO/architecture-repository
    CLIENT-B:
      git: { url: "git@github.com:your-org/client-b-architecture.git", branch: main, path: ../client-b-architecture }

enterprise:
  local: enterprise-repository
```

`arch-init` resolves this file and writes absolute paths to `.arch/init-state.yaml`, which all
tooling reads on startup. `arch-switch-engagement <name>` updates the active entry and
restarts a running backend. See [CLI & Backend](cli-and-backend.md).

&nbsp;

## `config/settings.yaml` — backend

```yaml
backend:
  port: 8000                  # TCP port (default 8000)
  log_path: .arch/backend.log # where a DETACHED backend writes; workspace-relative if
                              # not absolute. A foreground run (the container's, and any
                              # plain `arch-backend`) logs to stdout/stderr instead
  min_log_level: INFO         # DEBUG | INFO | WARNING | ERROR | CRITICAL
  slow_request_warning_s: 5   # log a warning for any request still running after this
  request_thread_dump_s: 20   # dump every thread's stack for a request still running
                              # after this — the diagnostic for a stuck request, so keep
                              # it well above the warning threshold

diagrams:
  archimate_type_markers: icons   # icons | labels
  sprite_scale: 1.5
  render_dpi: 150
  plantuml_limit_size: 16384

repo_init:
  default_branch: main
  commit_author_name: arch-switch-engagement
  commit_author_email: arch-switch-engagement@local.invalid
  engagement:
    # optional per-repo-kind overrides used by arch-switch-engagement --create
    default_branch: main
    commit_author_name: Architecture Bot
    commit_author_email: architecture-bot@example.com

storage:
  assurance:
    store_backend: sqlcipher              # sqlcipher | private-git | pocketbase
    signals_backend: sqlcipher-colocated  # sqlcipher-colocated | sqlite | encrypted
    archive_backend: standard             # standard | worm | s3-worm | azure-blob-worm
    max_classification: TLP:RED           # TLP:WHITE | TLP:GREEN | TLP:AMBER | TLP:RED
    activation_policy: manual             # manual | persistent — whether a newly started
                                          # process may open the store from the activation
                                          # gate by itself. 'manual' starts locked and needs
                                          # `arch-assurance unlock`; 'persistent' opens until
                                          # `arch-assurance lock`. Bounds application-level
                                          # access, not key extraction.

modules:
  sysml_v2_min:
    enabled: false

validation:
  viewpoint_enforcement: warn   # off | warn | ghost — default enforcement for a diagram/matrix's
                                 # viewpoint: application; overridable per application

guidance:
  # default --source for arch-import-guidance; ships pointing at the published
  # guidance catalog — pass --source to import from somewhere else
  default_source: https://raw.githubusercontent.com/mbauer83/architecture-modeling-guidance/refs/heads/main/guidance.yaml

viewpoints:
  execution_max_entities: 500              # hard cap on entities in a viewpoint execution result
  execution_default_entity_limit_mcp: 200  # MCP execute default when no limit argument is given
  execution_timeout_seconds: 10

assurance:
  neighbors_default_max_hops: 1        # hops when a neighbors request names none (hard clamp 4)
  neighbors_max_hops: 4                # upper bound any request's max_hops is clamped to (hard clamp 4)
  neighbors_max_nodes: 150             # node budget per traversal response (hard clamp 1000)
  neighbors_max_edges: 300             # edge budget per traversal response (hard clamp 2000)
  neighbors_time_budget_seconds: 2.0   # wall-clock budget; exceeding it aborts the whole request
```

These apply globally and are read at startup; they are not configurable via
`arch-workspace.yaml`. `validation.viewpoint_enforcement` and the `viewpoints:` execution
bounds are covered in full in [Viewpoints — schema
reference](viewpoints-schema.md#execution-result--bounds); `guidance.default_source` in
[Authoring guidance](../05-extensibility/guidance.md#importing).
The `storage.assurance` keys are written automatically by
`arch-assurance init` and `arch-assurance use-backend` — see
[Assurance: storage & confidentiality](../04-assurance/storage-and-confidentiality.md).
For `signals_backend`: **`sqlcipher-colocated`** (recommended) stores security-signal
snapshots inside the encrypted assurance store, behind the same unlock, classification,
and audit path; **`sqlite`** is the unencrypted public database — deprecated for
posture metrics, since findings then live outside the confidentiality boundary;
**`encrypted`** is a legacy alias for `sqlcipher-colocated` — the runtime tolerates it;
update the settings document to the explicit value yourself (see the
[upgrade guide](upgrade-guide.md#quarantine-and-blocking-findings)).
The `assurance:` traversal budgets bound `GET /api/assurance/nodes/{node_id}/neighbors` (the assurance
graph explorer): the size budgets produce deterministic partial results with frontier
node ids, while the time budget aborts the whole request with a retryable error; every
value is hard-clamped in code so misconfiguration can never unbound the traversal.

`modules:` overrides ontology and diagram-type module manifests for the current runtime.
Each key is a module name and currently supports one override: `enabled: true | false`.
Unset modules use their manifest defaults (`enabled` plus any `requires` capability or
module dependencies). Disabled modules stay in the complete vocabulary used for code
generation and schema export, but they are absent from runtime authoring guidance, type
validation, `/api/modules`, and write operations until the backend is restarted with the
module enabled.

&nbsp;

## Per-repository schemata (`.arch-repo/schemata/`)

```
.arch-repo/schemata/
  attributes.{entity-type}.schema.json
  frontmatter.entity.schema.json
  frontmatter.outgoing.schema.json
  frontmatter.diagram.schema.json
```

These extend or constrain the global ontology per repo. Engagement schemata must be supersets
of enterprise schemata, or promotion is blocked. Full detail in
[Attribute profiles & frontmatter schemata](../05-extensibility/schemata-and-profiles.md).

&nbsp;

## Document types (`.arch-repo/documents/*.json`)

Each file defines one document type — abbreviation, name, subdirectory, frontmatter schema,
required sections, and required/suggested entity links. See
[Document types](../05-extensibility/document-types.md).
