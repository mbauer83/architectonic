# Attribute Profiles & Frontmatter Schemata

Each repository may carry a `.arch-repo/schemata/` directory of JSON Schema files that extend
or constrain the global ontology for that repo.

```
.arch-repo/
  profiles.yaml                                           # named, reusable attribute profiles (optional)
  schemata/
    attributes.{entity-type}.schema.json                    # base attribute schema per entity type
    attributes.{entity-type}.{specialization-slug}.schema.json  # attached to one entity specialization
    frontmatter.entity.schema.json                          # constraints on entity frontmatter
    frontmatter.outgoing.schema.json                        # constraints on connection (outgoing) frontmatter
    frontmatter.diagram.schema.json                         # constraints on diagram frontmatter
    connection-metadata.{connection-type}.schema.json       # per-connection metadata block, per type
    connection-metadata.{connection-type}.{specialization-slug}.schema.json  # attached to one connection specialization
```

&nbsp;

## Attribute profiles

`attributes.{type}.schema.json` constrains the `properties:` section of entities of that
type. The `required` list enforces mandatory fields; `properties` declares their types and
allowed values. The GUI renders these as type-specific form fields and validates them on
write; an agent receives the same constraints as structured data before authoring.

For example, requiring a `rationale` and a `priority` enum on every `principle`:

```json
{
  "type": "object",
  "required": ["rationale", "priority"],
  "properties": {
    "rationale": { "type": "string" },
    "priority":  { "type": "string", "enum": ["Must", "Should", "Could", "Won't"] }
  }
}
```

&nbsp;

## Frontmatter schemata

`frontmatter.{entity|outgoing|diagram}.schema.json` constrains the YAML frontmatter fields
common to all entities, connections, or diagrams in the repo — the metadata layer above each
artifact's type-specific properties. These are **extend-only**: a repo may add fields and
tighten constraints, and the verifier checks every write against them.

&nbsp;

## How a specialization contributes attributes

A specialization (see [Ontology modules](ontology-modules.md#specializations)) contributes
attribute constraints through any combination of three mechanisms:

- **Inline** `attributes: {}` on the specialization's own declaration.
- **A dedicated attachment file**, `attributes.{entity-type}.{specialization-slug}.schema.json`
  — a standalone JSON Schema, filename-scoped to that one slug.
- **Named-profile bindings** — `profiles: [name, ...]` referencing reusable profiles
  declared in `profiles.yaml` (below). Unlike the first two, a named profile is shared:
  the same profile can be bound by several specializations, so cross-cutting attribute sets
  (a shared `ai-provenance` block, an `ownership` block) are declared once.

Each mechanism compiles to a JSON Schema fragment (`required` for `required`-level
attributes, the extension keyword `x-recommended` for `recommended`-level ones — JSON Schema
has no native "recommended", so the verifier checks it explicitly rather than relying on
`jsonschema` itself).

&nbsp;

## Named attribute profiles

`.arch-repo/profiles.yaml` declares reusable profiles a specialization can bind by name.
The file carries a format version and each profile carries a content version:

```yaml
profile_schema: 1              # declaration format version (a typed error if unrecognised)
profiles:
  ai-provenance:
    version: 1                 # content version — bumped when the profile's attributes change
    attributes:
      Model Provider: { type: string, level: required }
      Training Cutoff: { type: string, level: optional }
```

A specialization binds one or more by name, in declaration order:

```yaml
specializations:
  entity:
    application-component:
      - slug: ai-inference-service
        profiles: [ai-provenance]
        attributes:                # its own inline attributes still apply, and win last
          Endpoint: { type: string, level: required }
```

The shipped ontology module may also ship a registry; a repo-level profile of the same name
overrides the shipped one. Binding a name that no registry defines is a **structural
(Class A) error** — see [failure semantics](#failure-semantics).

Connection specializations bind profiles by the identical mechanism (`specializations:` →
`connection:` block), and their per-connection metadata resolves through the same pipeline.

&nbsp;

## Effective schema and resolution order

An element's **effective attribute schema** is its fragments merged in a fixed,
deterministic order (a connection's effective metadata schema resolves identically):

1. the base-type schema (`attributes.{type}.schema.json` / `connection-metadata.{type}.schema.json`);
2. each applied specialization's **bound named profiles**, in declaration order;
3. each applied specialization's **own** profile last (inline `attributes:` then its
   attachment file) — so the specific always wins over a shared profile it composes.

A property redefined incompatibly across fragments (same name, different `type`) is a
conflict; any other redefinition (e.g. a different `default`) resolves last-writer-wins. An
attachment file whose `{specialization-slug}` segment names no specialization declared for
that type is a verifier warning (orphaned attachment) rather than silently ignored.

&nbsp;

## Failure semantics

A conflict's blast radius decides how it fails:

- **Class A — structural.** A binding to a profile name no registry defines leaves the
  registry itself ill-defined. On an engagement repo this **aborts startup** (the model
  cannot be trusted to resolve at all); on the enterprise repo it is a warning. Fix the
  binding, then restart.
- **Class B — scoped (quarantine).** Two fragments disagree on an attribute's `type`, so
  one `(type, specialization)` pair has no unambiguous effective schema. The rest of the
  model stays well-defined, so the failure is confined to that pair: reads continue, but a
  create or edit onto it is **refused at the write boundary** — every transport (GUI, REST,
  MCP) funnels through the same gate, and the verifier reports the conflict as a blocking
  error (`E043` for entities, `E045` for connections). The authoring GUI shows a banner
  naming the conflict and disables submit; the connection editor does the same. Quarantine
  is computed on demand and never persisted, so it self-clears the moment the conflicting
  profiles or bindings are reconciled.

`arch-repair` reports each quarantining conflict and proposes concrete resolutions — rename
the attribute, align its type, or unbind one contributing profile — as manual instructions.
It never rewrites operator-authored content automatically.

The rationale for this classification, and why quarantine is enforced at a single write
boundary rather than persisted, is recorded in [ADR: Profile failure
semantics](../../engagements/ENG-ARCH-REPO/architecture-repository/docs/adr/platform-core/ADR@1784674023.8alNxn.profile-failure-semantics-blast-radius-classification-and-single-boundary-quarantine.md).

&nbsp;

## Connection metadata schemata

`connection-metadata.{connection-type}.schema.json` constrains the per-connection metadata
block — the fenced YAML block immediately under a connection's `### ` heading in an
`.outgoing.md` file, distinct from the file's shared frontmatter. Besides `specialization`
(see [Ontology modules](ontology-modules.md#specializations)), the block holds whatever
attributes the connection type's effective metadata schema declares, authored through the
same typed fields the entity forms use. A connection specialization attaches its own
attributes exactly as an entity one does —
`connection-metadata.{connection-type}.{specialization-slug}.schema.json`, plus inline
`attributes:` and named-profile bindings — and resolves through the same order and the same
quarantine rules. Like the other schemata here, this one is opt-in per connection type —
absent any schema, the metadata block validates freely.

The shipped ArchiMate influence schema provides an optional `polarity` property with
`positive` and `negative` values. ArchiMate diagrams render these as a green plus or red
minus on the relationship; omitting the property preserves the standard unmarked notation.

&nbsp;

## Promotion superset rule

An engagement repo's schemata must be supersets of the enterprise repo's schemata — every
property and required field in an enterprise schema must also appear in the corresponding
engagement schema. Promotion is blocked, with a per-violation message, when this does not
hold, so a promoted entity always satisfies the enterprise constraints after transfer.

---

*Next: [Document types →](document-types.md)*
