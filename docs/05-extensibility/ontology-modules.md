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

Adding a module is five steps: create the package, define `entities.yaml`, optionally define
`connections.yaml`, implement the `module` object, and register it in
`src/infrastructure/app_bootstrap.py`. A scaffold helper generates the package skeleton so
you start from a working module.

&nbsp;

## Guidance externalization (license compliance)

A module's `create_when`/`never_create_when` slots may ship **empty** — `archimate_4`
does, because its authored guidance text derives from licensed material that is never
committed to this repository. Guidance is imported per deployment with
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

An entity or connection carries **at most one** specialization slug at a time (an instance
has exactly one parent type, so "one specialization" is the natural cardinality — the
catalog itself stays plural, enumerating every *available* option per parent type).

- **Entities**: the `specialization: <slug>` frontmatter field, set via
  `artifact_create_entity`/`artifact_edit_entity` (empty string clears it).
- **Connections**: a fenced YAML metadata block immediately under the connection's `### `
  heading in `.outgoing.md` — never the file's shared frontmatter, which covers every
  connection in the file — carrying `specialization: <slug>` (and open to future
  per-connection metadata). Set via `artifact_add_connection`/`artifact_edit_connection`.

The verifier checks every assignment:

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
