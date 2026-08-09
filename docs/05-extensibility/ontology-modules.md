# Ontology Modules

An ontology module is a self-contained vocabulary of entity types, connection types, and
permitted-relationship rules. The system loads every registered module at startup and merges
them into one global `ModuleRegistry`. New ontologies — SysML, TOGAF, a domain-specific
language — drop in without touching the core.

Full contract and a complete loader example:
[`src/ontologies/README.md`](../../src/ontologies/README.md).

&nbsp;

## Shipped modules

| Module | Vocabulary | Domain (`hierarchy[0]`) |
|---|---|---|
| `archimate_4` | ArchiMate 4.0 — the canonical default | motivation, strategy, business, application, technology, implementation, common |
| `sysml_v2_min` | A minimal SysML v2 vocabulary (parts, actions); shipped but disabled by default | its own domain when enabled |
| `assurance` | STPA / CAST / GRC types (stored in the encrypted assurance store, not git) | assurance |

&nbsp;

## Anatomy of a module

```
src/ontologies/my_ontology/
  __init__.py          # exposes `module` satisfying the OntologyModule protocol
  entities.yaml        # one entry per entity type
  connections.yaml     # connection types + permitted_relationships (optional)
  _loader.py           # optional; archimate_4 loader is the template
```

An `entities.yaml` entry carries `prefix` (ID prefix, e.g. `PDF@…`), `hierarchy` (domain path
segments; `hierarchy[0]` is the grouping domain), `classes` (element classes used by diagram
filters and connection rules), and `create_when` / `never_create_when` authoring guidance.

`permitted_relationships` rules use `[source, target, [conn-short-names]]`, where source and
target accept a literal type, `@class`, `@all`, `@same`, or a list — so one rule can cover a
whole element class.

&nbsp;

## Rules the registry enforces at startup

- **Type-name uniqueness** — entity and connection type names are globally unique across all
  registered ontologies.
- **Single class ownership** — each element class is declared by exactly one module; others
  reference it without redeclaring.
- **Protocol compliance** — every module must satisfy the `OntologyModule` protocol, checked
  by `tests/domain/test_protocol_compliance.py` on every run.
- **Domain registration** — each new `hierarchy[0]` domain needs a color/label entry in
  `tools/gui/src/ui/lib/domains.ts` so its chip renders correctly.
- **Coherent classification levels** — if a module declares `classification_levels`, exactly one
  level keys relationships, no level above it narrows them, and at least one carries attributes.

Adding a module is five steps: create the package, define `entities.yaml`, optionally define
`connections.yaml`, implement the `module` object, and register it in
`src/infrastructure/app_bootstrap.py`. A scaffold helper generates the package skeleton so
you start from a working module.

&nbsp;

## Classification levels

An element is classified through a chain — its **domain**, its **entity type**, and optionally a
**specialization**. The chain has always been expressible: `hierarchy` in `entities.yaml` declares
the domain segments, and `specializations.yaml` declares the rest. What `classification_levels`
adds is the *characterisation* of each rung, so a consumer can ask what a level is called, whether
it is required, and what it governs — rather than hard-coding the answers.

```yaml
classification_levels:
  - id: domain
    label: Domain
    from: hierarchy          # the segments entities.yaml already declares
    required: true
  - id: entity_type
    label: Entity type
    from: type
    required: true
    keys_relationships: true # permitted_relationships are keyed here
    carries_attributes: true
  - id: specialization
    label: Specialization
    from: specializations
    narrows_relationships: true  # restrict_relationships / restrict_endpoints
    carries_attributes: true     # narrows the parent level's schema
```

`from:` points at data the module already declares, so the block restates nothing.

**The block is optional.** A module that omits it gets exactly this shape as the derived default,
which is the behaviour every consumer previously assumed — so `sysml_v2_min` and `assurance` declare
nothing and are right not to.

One declaration answers five questions that were previously answered in five places:

| Question | Answered by |
|---|---|
| Which pickers does refinement offer, in what order? | the level list |
| When should a drawn relation be verified? | both ends reached the level with `keys_relationships` |
| Is a violation a refusal or a warning? | `keys_relationships` → **E126**, blocks · `narrows_relationships` → **W128/W129**, warns |
| Which attribute schema applies? | the deepest level reached with `carries_attributes` |
| May this element be lifted yet? | every `required: true` level reached |

The third row is the one that makes this more than convenient: the two-tier verification — a
type-level refusal against a specialization-level narrowing — becomes a *consequence* of the
declaration rather than a special case inside the verifier.

&nbsp;

## Guidance externalization

A module's `create_when`/`never_create_when` slots may ship **empty** — `archimate_4`
does: its guidance is a separately published, independently versioned corpus, and the
import mechanism must equally serve deployments whose own corpora are licensed for
internal use only — so imported guidance is never committed, whatever its origin.
Guidance is imported per deployment with
`arch-import-guidance` and layered along the module's declared concept hierarchy
(domain → entity type → specialization for `archimate_4`), with the empty state
explicitly signaled rather than silently blank. The full story — hierarchy levels, the
document format, importing, precedence — is on the
[Authoring guidance](guidance.md) page.

&nbsp;

## Specializations

A specialization narrows a base entity or connection type — e.g. `business-collaboration`
narrows `collaboration`, `responsibility-assignment` narrows `archimate-assignment`. Both
kinds live in one catalog, keyed by `(module, concept_kind, parent_type, slug)`:

- **Module-level library**: a module's `specializations.yaml` ships an informative starter
  set (names + parent types; guidance text empty, subject to the same externalization rule
  as `create_when`/`never_create_when` above).
- **Repo-level extension**: `.arch-repo/specializations.yaml` at the enterprise and
  engagement tiers adds repo-specific specializations on top of the module library.

Each entry may declare `restrict_relationships` (entity specializations: an allow-list of
`(connection-type, source-type, target-type)` triples the entity may participate in) or
`restrict_endpoints` (connection specializations: an allow-list of source/target type pairs).
A specialization's restrictions may only *narrow* what its parent type already permits, never
broaden it — checked at catalog-load time.

### Assigning a specialization

An entity or connection may carry **several** specialization slugs (ArchiMate §15.2) — a
concept has one parent type but can be several kinds of it at once, and the attribute
schemata of every applied specialization merge. The **key stays singular** and its *value*
carries the shape: one slug is written as a scalar, so the many files holding one are
byte-identical to what they were, and several as a list.

- **Entities**: the `specialization:` frontmatter field, set via
  `artifact_create_entity`/`artifact_edit_entity` (an empty list clears it).
- **Connections**: a fenced YAML metadata block immediately under the connection's `### `
  heading in `.outgoing.md` — never the file's shared frontmatter, which covers every
  connection in the file — carrying `specialization:` (and open to future per-connection
  metadata). Set via `artifact_add_connection`/`artifact_edit_connection`.

Carrying several on one connection is also what keeps connection identity intact. A
connection is identified by `(source, target, type)`, so two connections between the same
endpoints with the same type — distinguished only by their specializations — are one
connection, and the second reads as a duplicate (W120). One connection carrying both says
what the model means without changing what a connection is.

The verifier checks **every applied slug**, not just the first — each may narrow endpoints or
relationships on its own, so checking one left the rest unenforced silently for as long as
nothing carried two:

| Code | Severity | Meaning |
|---|---|---|
| E160 | error | Connection specialization slug is not declared in any catalog. |
| E161 | error | Connection specialization slug is declared, but for a different connection type. |
| E170 | error | Entity specialization slug is not declared in any catalog. |
| E171 | error | Entity specialization slug is declared, but for a different entity type. |
| W128 | warning | Connection specialization's `restrict_endpoints` doesn't cover the connection's actual (source-type, target-type) pair. |
| W129 | warning | An endpoint entity's own specialization's `restrict_relationships` doesn't cover the connection's actual (type, source-type, target-type) triple for that entity's role. |

Attribute constraints attach to a specialization inline, via a dedicated attachment file,
or through named-profile bindings — they never redefine the specialization itself. See
[How a specialization contributes attributes](schemata-and-profiles.md#how-a-specialization-contributes-attributes).

### Discovery

`artifact_authoring_guidance` (MCP) and `GET /api/authoring-guidance` (REST) enumerate every
available specialization per type: each `entity_types[]` entry carries its own
`specializations` list (empty when the type has none declared), and a top-level
`connection_types` block lists connection types that have at least one specialization
(connection types with none are omitted, since — unlike entity types — they have no other
guidance entry to attach an empty list to). The GUI's entity create/edit forms and the
connection-editing panel use this to populate a specialization picker scoped to the chosen
type; entity listings, entity detail, and connection listings display the assigned
specialization (as a `«slug»` badge) when one is set.

### Rendering

A specialization renders as a guillemet stereotype — `«Business Collaboration»`, e.g. —
appended to the entity's or connection's label, distinct from the ASCII `<<connection-type>>`
stereotype used for relationship types (both can appear together; the specialization
guillemet renders even where the connection-type stereotype is suppressed by the existing
`show_stereotype` heuristic). When the specialization declares its own notation, it overrides
the parent type's: `icon` replaces the sprite glyph, `color` adds a background override on
entity boxes, and `line_style`/`label_marker` style connections (a declared `line_style` is
skipped on a connection whose arrow already carries an automatic layout-direction hint,
rather than risk an incorrectly merged arrow token). Absent any of these, rendering falls
back to the parent type's notation unchanged.

&nbsp;

## Viewpoints

`ViewpointDefinition`s follow the identical two-tier pattern as specializations — a module's
`viewpoints.yaml` ships a small starter library, `.arch-repo/viewpoints.yaml` extends it at
the enterprise and engagement tiers, and the effective catalog is the merge. See
[Viewpoints](../03-modeling/viewpoints.md) for the concept and
[Viewpoints — schema reference](../reference/viewpoints-schema.md) for the full declaration
grammar.

---

*Next: [Diagram-type modules →](diagram-type-modules.md)*
