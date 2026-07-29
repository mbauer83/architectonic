# Architecture Repository: Documentation

This directory contains semi-structured, non-model documentation for the architecture repository.
The ArchiMate model lives in `model/`; diagrams live in `diagram-catalog/`; everything else
(decisions, standards, specifications) lives here.

## Structure

| Subdirectory | Purpose |
|---|---|
| `adrs/` | Architecture Decision Records — one file per decision |
| `standards/` | Coding/design standards and guidelines |
| `specs/` | Technical specifications |

Additional subdirectories may be added as needed.

## Authoring Conventions

Documents are plain markdown — **no YAML frontmatter**. The `doc-id` used by the framework query
server is the filename stem (e.g., `adr-001-archimate-next-adoption`). Metadata such as status,
authors, and date is expressed inside the required section headings.

### Required sections by doc-type

**ADR** (`adrs/`):

```
## Status
## Context
## Decision
## Consequences
```

**Standard** (`standards/`):

```
## Purpose
## Scope
## Rules
## Rationale
```

**Specification** (`specs/`):

```
## Overview
## Requirements
## Specification
## Acceptance Criteria
```

## Cross-References

To link from one document to a specific section of another, use:

```markdown
[@DOC:target-doc-id#section-id](relative/path/to/doc.md)
```

- `target-doc-id` — the filename stem of the target document
- `section-id` — the slugified heading (lowercase, spaces → hyphens)
- The path must be valid relative to the current file

Example:

```markdown
See [@DOC:adr-002-markdown-file-based-approach#decision](adr-002-markdown-file-based-approach.md)
for the related file-format decision.
```

Cross-references are indexed by the `arch-mcp-framework` server, enabling reference graph
traversal across all documents in this directory.

## Lifecycle status

Model entities carry a lifecycle status with these transition rules: content that has been
reviewed and reflects the implemented or decided state reads `active`; `draft` is reserved
for genuinely in-flight items still being shaped. Saving an artifact never changes its
status (editing is not reviewing) — activation happens only through an explicit review or
promotion act, and deprecation is likewise a separate explicit act. A model-wide reviewed
transition on 2026-07-18 moved the stable population to `active`; new entities start as
`draft` until their first review.
