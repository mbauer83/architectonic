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
  "required_entity_type_connections": ["requirement", "@internal-behavior-element"],
  "suggested_entity_type_connections": ["principle", "goal", "@all"]
}
```

| Field | Purpose | On failure |
|---|---|---|
| `frontmatter_schema` | JSON Schema for the document's YAML frontmatter. Fields beyond the built-in `title` / `status` / `keywords` render as type-specific form fields in the GUI. | Validation error on write |
| `required_sections` | `## Heading`s that must be present in the body | E154 |
| `required_entity_type_connections` | Entity-type terms of which at least one matching entity must be linked from the body (a concrete type, `@all`, or any element class as `@class`) | E155, blocks write |
| `suggested_entity_type_connections` | Recommended links; surfaced in the GUI as blue "Suggested entity links" notices | not enforced |

Element-class terms (the `@…` form, for example `@internal-behavior-element`) use the same
syntax as the connection ontology, so a document type can require a link to *any* entity of a
behavioural class without naming each concrete type.

---

*Next: [Ontology modules →](ontology-modules.md)*
