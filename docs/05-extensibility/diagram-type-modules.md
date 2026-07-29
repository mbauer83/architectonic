# Diagram-Type Modules

A diagram-type module declares which entity and connection types a view accepts and how it
renders. Most ArchiMate views are config-only; families with their own notation bring a
custom renderer. Full contract:
[`src/diagram_types/README.md`](../../src/diagram_types/README.md).

&nbsp;

## The `config.yaml` contract

```yaml
name: archimate-application      # registry key; matches diagram_type in artifacts
ontology: archimate_4            # ontology package supplying the base vocabulary
filter:
  hierarchy_level: { index: 0, values: [application, common] }   # which entity types appear
grouping:
  by_field: hierarchy_0
  stereotype_pattern: "{hierarchy_0|capitalize}Grouping"
layout:
  nesting_connection_classes: [nesting]   # draw children inside parent frames
  flow_connection_classes: [dynamic]      # draw directed flow arrows
guidance:
  when_to_use: "…"                         # returned to agents via artifact_authoring_guidance
  when_not_to_use: "…"
ui:
  label: "ArchiMate Application"                    # how the type names itself everywhere
  description: >-                                   # one sentence, shown under the label
    The application layer: software components, services, interfaces, and the data they manage.
  diagram_only_types:
    - entity_type: local-note
      label: Local note
      plural: Local notes
      include_in_global_search: false       # default; diagram pickers still include it
```

Only `name` is required for the module to load; every other field falls back to a built-in
default.

`ui.label` and `ui.description` are required of a registered type, and
`tests/diagram_types/test_diagram_type_presentation.py` fails if either is missing. Both reach every
type picker and the create-diagram menu, and neither has a usable default: the label falls back to
the title-cased registry key, which mangles acronyms and product names, and an absent description
shows as a blank line. `DiagramTypeBase.ui_config` reads them from the type's own `config.yaml`, so
declaring them there is all a new type needs to do — including a type that assembles the rest of its
configuration from several sources and sets `_ui_config` itself.

&nbsp;

## Rendering: config first, custom only when needed

The `GenericPumlRenderer` handles baseline config-backed PlantUML, and the shared
`ArchimatePumlRenderer` layers ArchiMate behavior on top. You do **not** write a renderer for
a new domain view, a different filter, or different grouping/layout.

A custom renderer (implementing the `DiagramRenderer` protocol) is needed when the format is
not PlantUML ArchiMate (matrix tables, sequence, ER), when rendering needs entity-specific
logic config cannot express, or when the diagram owns diagram-scoped state that affects
rendering (activity swimlanes, C4 boundaries). The `matrix` type is the reference case: it
renders Markdown instead of PlantUML.

&nbsp;

## Diagram-only entity types

Some types exist only inside a diagram's `diagram-entities:` frontmatter and are never written
to the model store (swimlanes, sequence participants, C4 boundaries). They are declared in
`ontology.yaml` (structure and semantics) plus `config.yaml` (UI label and plural). Structural
links between them live in the diagram's `connections:` list, not as entity properties.
They are excluded from global search by default so model entities retain priority. Set
`include_in_global_search: true` on the UI entry only when the diagram-owned construct is
meaningful outside its host diagram; opted-in entries still sort below model entities.

&nbsp;

## Diagram-owned connection types and connection bindings

A diagram module can declare **diagram-only connection types** — structural edges that live
in the diagram's `connections:` list rather than as model connections. They are declared in
`ontology.yaml` alongside entity types, and they carry the same metadata fields
(`relationship_kind`, `symmetric`, `puml_arrow`).

The `datatype` module is the reference case. It owns five `dt-*` connection types
(`dt-association` through `dt-dependency`), each tagged with a `relationship_kind` matching
the ArchiMate backing type family. When a `dt-*` edge connects two classifiers that are each
bound to a Data Object, the verifier checks that a backing model connection with a
corresponding `relationship_kind` exists — and surfaces structured `details` and `actions` in
the error payload when it does not.

**Connection bindings** record this correspondence. In the diagram's `bindings:` list, a
connection binding entry looks like:

```yaml
bindings:
  - id: bind-e1
    subject: { kind: connection, id: e1 }
    correspondence_kind: represents
    target: { connection_id: "DOB@1---DOB@2@@archimate-association" }
```

The GUI write path strips `backing_conn_id` from `_connections` items and converts them to
proper binding entries before persisting, so MCP callers can pass `backing_conn_id` as a
convenience field and the storage layer normalises it.

&nbsp;

## Model-backed projection (C4)

Diagram types that derive content from the ArchiMate graph may implement the `ViewProjector`
capability. C4 uses one projection engine for preview, render, and refresh, so the live
preview an author sees is structurally identical to the saved render — visible in the
"Create Diagram" screen as auto-derived entities with an inline "Verification passed" check
and a "Show PUML source" toggle.

&nbsp;

## Rules the registry enforces

Every module satisfies the `DiagramTypeModule` protocol; `name` matches its registry key;
`effective_entity_types()` and `effective_connection_types()` only return types present in
the registry. A protocol-compliance test checks every registered type on each run. A scaffold
helper generates a new diagram-type package wired into the registry.

---

*Next: [Hexagonal architecture →](hexagonal-architecture.md)*
