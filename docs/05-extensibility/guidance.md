# Authoring Guidance

Authoring guidance is the per-concept "create when / never create when" text that the
GUI modeling wizard and the `artifact_authoring_guidance` MCP tool serve while you
model: what a concept is for, when to create one, and when something else is the better
fit. It covers both element types and relationship types. This page covers where guidance
comes from, how it is layered along a module's concept hierarchy, and how to import it.

&nbsp;

## Why guidance is imported, not bundled

The `archimate_4` module ships its `create_when`/`never_create_when` slots **empty** —
the authored guidance text derives from licensed material and lives outside this
repository, never committed (the same rule that keeps the ArchiMate specification text
out of git). Until an import has run, the guidance surfaces do not fall silent:
`artifact_authoring_guidance` (MCP) and `GET /api/authoring-guidance` (REST) return
`guidance_status: "empty"` plus a `guidance_hint` naming the import command, and the GUI
modeling wizard shows the same hint — never a blank string that could be misread as "no
restrictions apply".

Guidance is shown **in the wizards only**. The ordinary create/edit forms stay out of its
way: someone editing an existing element or relationship has already made the modeling
decision, and a panel of prose there would crowd out the fields. The wizards are where a
choice is still open — which element type answers this question, which relationship to
accept between two elements — so that is where the text earns its space.

&nbsp;

## Layered guidance: the hierarchy

Guidance attaches to any level a module declares, and is **composed additively along the
concept's ancestry** when authoring support is served. Above every module sits one
alias-independent **workspace** level; each module then declares its own ordered levels,
rooted in a per-module **meta-ontology** level. For `archimate_4` the full order is:

```
workspace  →  meta-ontology  →  domain  →  entity type  →  specialization
```

- **Workspace** — one text for the cross-cutting stance that holds regardless of which
  module you author in (ArchiMate, assurance, SysML, …). Broadest of all; prepended to
  *every* concept's guidance, even one whose module is unknown.
- **Meta-ontology** — one node per module (id = the module alias), for guidance that
  spans the whole module above its domains (e.g. naming and conceptualization stances).
  Relationship types hang here too: a relationship is declared for the whole
  meta-ontology, not for one domain.

Asking for guidance on, say, an `application-component` with the `service`
specialization serves the specialization's guidance *plus* its ancestors' context — the
entity type's, the application domain's, the module's meta-ontology, and the workspace
stance — so the broad modeling intent frames the specific rule. In the wizard the
broader-level context renders above the type's own text as clearly labeled sections, and
each suggested relationship can disclose its own `create_when`/`never_create_when`.

The module levels are owned by the module's ontology, never by a guidance document — a
document cannot invent levels or nodes, and every placement is validated at import time
rather than surfacing as a runtime surprise. The workspace level is the one exception to
"the module owns it": it sits above every module, so its text is author-defined.

&nbsp;

## The guidance document format

A guidance document is YAML with a `guidance_format` version header. The current format
is **4**, and **its nesting is the hierarchy**: the alias is the module's root node, each
of its keys is a node one level down, and so on until the level whose concepts arrive as
type slots.

```yaml
guidance_format: 4
workspace: "One cross-cutting stance, above every meta-ontology."
meta_ontologies:
  archimate-4:                      # the module's root node
    context: "Naming and conceptualization spanning the whole meta-ontology."
    connection_types:               # relationship types: meta-ontology-wide, so they sit here
      archimate-assignment:
        create_when: "…"
        never_create_when: "…"
        specializations:
          responsibility-assignment: { create_when: "…", never_create_when: "…" }
    motivation:                     # a node of the next declared level (domain)
      context: "Why the architecture is shaped this way."
      entity_types:                 # the types this node is the declared parent of
        goal: { create_when: "…", never_create_when: "…" }
```

- structural keys are `context`, `entity_types`, `connection_types`, `specializations`,
  `create_when`, `never_create_when` — everything else is a node id;
- an entity type sits under the node its module declares as its parent. Filing `goal`
  under `strategy` is an **error the importer reports**, not guidance served under the
  wrong framing — which is what the nesting buys over flat, level-keyed maps;
- `connection_types` belongs at the root: a relationship type carries no domain;
- a module with a different tree (shallower, deeper, differently named) needs no format
  change — the document nests as deeply as that module declares levels;
- `workspace:` is a top-level sibling of `meta_ontologies:`, never an alias — one text,
  imported to its own cache file, prepended to every concept's chain.

Only the current format imports. An earlier-format document already in the cache is
restructured **offline** by the upgrade tool — it re-nests each entity type under the
domain its module declares and folds the older per-topic workspace map into one text; see
the [upgrade guide](../reference/upgrade-guide.md).

&nbsp;

## Importing

```sh
uv run arch-import-guidance                                             # the configured source
uv run arch-import-guidance --dry-run                                   # validate and report only
uv run arch-import-guidance --source guidance.yaml                      # a local file instead
uv run arch-import-guidance --source guidance.yaml --module archimate_4 # only this module alias
uv run arch-import-guidance --source guidance.yaml --strict             # abort on any unknown key
```

The importer validates the document against the registered module — every node against
its declared level and parent, every entity type against the node it is filed under,
every relationship type and specialization slug against the module's catalogs — then
writes one **deployment-level cache** —
`~/.config/arch-repo/guidance-cache/<alias>.guidance.yaml` per module (plus a provenance
sidecar `<alias>.guidance.meta.yaml` recording source, SHA-256, format version, and
matched/unmatched counts), and, when the document carries a `workspace:` section, one
alias-independent `workspace.guidance.yaml` (with its own sidecar). Guidance is a
deployment concern, not a per-repository one: one running
instance imports one guidance source, applied to whichever repos it serves — never
split by engagement/enterprise tier, and never committed to either repo. `--allow-http`
permits a plain-HTTP source (HTTPS is required by default). Restart the backend to pick
up a newly imported cache.

**Precedence:** module-inline guidance (empty by default) < the imported deployment
cache. Committed repository declarations are never overridden by guidance.

**Where the default source lives:** `guidance.default_source` in `config/settings.yaml`, which
points at the published guidance document. `--source` overrides it, so an operator serving their
own guidance changes one setting rather than every invocation. Nothing is fetched until you run
the import — the setting names a location, it does not make the software call home.

&nbsp;

## Guidance and attribute schemata

Guidance says *when* to create a concept; attribute profiles and frontmatter schemata
say *what shape* it has — including the attributes a specialization contributes. Both
ride the same authoring-guidance payload, so one call answers "should I create this?" and
"what fields does it have?". See
[Attribute profiles & frontmatter schemata](schemata-and-profiles.md).

---

*See also: [Ontology modules](ontology-modules.md) · [CLI & backend → Guidance import](../reference/cli-and-backend.md#guidance-import)*
