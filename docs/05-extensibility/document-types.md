# Document Types

Documents (ADRs, standards, specifications, and your own kinds) are defined by JSON files
under `.arch-repo/documents/`. The filename without `.json` is the `doc-type` frontmatter
value used in document files.

```json
{
  "abbreviation": "STD",
  "name": "Standard",
  "subdirectory": "standards",
  "frontmatter_schema": {
    "type": "object",
    "required": ["title", "status"],
    "properties": {
      "title":      { "type": "string" },
      "status":     { "type": "string", "enum": ["draft", "accepted", "rejected", "superseded"] },
      "applies_to": { "type": "array", "items": { "type": "string" } },
      "date":       { "type": "string" }
    }
  },
  "required_sections": ["Scope", "Motivation", "Summary", "Specification"],
  "required_connections": ["requirement", "@internal-behavior-element", "doc:adr"],
  "suggested_connections": ["principle", "goal", "diagram:c4-container"],
  "sections": [
    { "name": "Specification", "required_connections": ["requirement"] }
  ]
}
```

| Field | Purpose | On failure |
|---|---|---|
| `frontmatter_schema` | JSON Schema for the document's YAML frontmatter. Fields beyond the built-in `title` / `status` / `keywords` render as type-specific form fields in the GUI. | Validation error on write |
| `required_sections` | `## Heading`s that must be present in the body | E154 |
| `required_connections` | Terms of which at least one match must be linked from the body | E155, blocks write |
| `suggested_connections` | Recommended links; surfaced in the GUI as blue "Suggested links" notices | not enforced |

Both lists may also be declared per section, under `sections[].required_connections` /
`sections[].suggested_connections`, where the link has to sit inside that section. An unmet
section requirement is **E156**; a section naming a term that does not expand is **W157** rather
than an error, because a typo in a schema should not make somebody's document unwritable.

## Reference terms

A term names one of three vocabularies:

| Form | Names | Example |
|---|---|---|
| bare | one entity type | `requirement` |
| `@class` | every entity type in an element class, using the connection ontology's own class names | `@internal-behavior-element` |
| `@all` | any entity | `@all` |
| `doc:<type>` | a document of that `doc-type` | `doc:adr` |
| `diagram:<type>` | a diagram of that `diagram-type` | `diagram:c4-container` |
| `doc:@all` / `diagram:@all` | any document / any diagram | `doc:@all` |

The vocabularies do not share a namespace: `requirement` requires an *entity* of that type, and a
linked document called `requirement` would not satisfy it.

A `diagram:` term naming a type this deployment does not register — the assurance diagram types
need the confidential store — is reported as **W159** rather than refused. A stored diagram of that
type still satisfies it, so a template stays usable on a host that cannot create one.

The earlier `required_entity_type_connections` / `suggested_entity_type_connections` spelling is
still accepted, and reads as a list of entity terms. Schemas are not rewritten on upgrade.

---

*Next: [Ontology modules →](ontology-modules.md)*
