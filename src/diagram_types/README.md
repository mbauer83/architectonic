# Diagram Type Modules

Each subdirectory is a *diagram type module* — a unit that declares which entity and connection types a diagram view accepts, and how those diagrams are rendered. The system loads all registered diagram types at startup and exposes them via the `ModuleRegistry`.

## Structure

```
src/diagram_types/
  c4/                      ← C4 diagram type family
    __init__.py
    _type.py               ← shared loader for the built-in C4 view family
    renderer.py            ← PlantUML renderer
    _resolve.py            ← C4 state resolution (model-backed + standalone)
    _projection.py         ← C4 projection engine + strategy registration
    _navigation.py         ← C4 parent/child diagram navigation
    system_context/        ← C4 level 1 view with mapped diagram-owned entities
      __init__.py
      config.yaml
      ontology.yaml
    container/             ← C4 level 2 view
      __init__.py
      config.yaml
      ontology.yaml
    component/             ← C4 level 3 view
      __init__.py
      config.yaml
      ontology.yaml
  archimate/               ← ArchiMate diagram type family
    __init__.py
    _type.py               ← shared loader for config-backed ArchiMate views
    application/           ← one domain view
      __init__.py
      config.yaml
    business/
      __init__.py
      config.yaml
    implementation/
      __init__.py
      config.yaml
    layered/               ← multi-domain view
      __init__.py
      config.yaml
    motivation/
      __init__.py
      config.yaml
    strategy/
      __init__.py
      config.yaml
    technology/
      __init__.py
      config.yaml
  activity/                ← UML activity view with swimlane diagram-entities
    __init__.py
    config.yaml
    ontology.yaml          ← activity-specific entity/connection type ontology
    renderer.py
  sequence/                ← UML sequence view
    __init__.py
    config.yaml
    ontology.yaml
    renderer.py
  matrix/                  ← free-ontology (accepts all entity types)
    __init__.py
    config.yaml
  _config_type.py          ← config-backed loader for ontology-bound views (shared)
  __init__.py              ← register_default_diagram_types()
```

## `config.yaml` schema

```yaml
name: archimate-application          # (required) registry key; matches diagram_type in artifacts
ontology: archimate_4                # ontology package under src/ontologies/

filter:
  hierarchy_level:
    index: 0
    values: [application, common]
# EntityTypeInfo.hierarchy[0] is the domain/layer segment under model/.
# Omit filter entirely for free-ontology kinds that accept everything.

includes: []
# ArchiMate diagram types use selective injection at render time: _archimate-stereotypes.puml
# and _archimate-glyphs.puml are inlined automatically via inject_includes(). Do not list
# them here — they are not included as static !include directives.

grouping:
  by_field: hierarchy_0              # groups entities by EntityTypeInfo.hierarchy[0]
  stereotype_pattern: "{hierarchy_0|capitalize}Grouping"
  # PlantUML stereotype for the frame; {hierarchy_0|capitalize} → "ApplicationGrouping"

layout:
  nesting_connection_classes: [nesting]
  # Connection classes (from `classes` in entities.yaml) that produce visual nesting in the
  # rendered diagram. Connections of these classes draw child entities inside parent frames.

  flow_connection_classes: [dynamic]
  # Connection classes that produce directed flow arrows (as opposed to structural lines).

guidance:
  when_to_use: >-
    Human-readable prose: when an author should choose this diagram type.
  when_not_to_use: >-
    Human-readable prose: when to prefer another diagram type instead.
  # Consumed by write_guidance() and returned to AI agents via artifact_authoring_guidance().

element_classes:                     # element class vocabulary for this diagram type
  step:
    description: An entity type that can appear in a steps/sequence array
  grouping:
    description: A grouping or partitioning entity

ui:
  label: "Application View"
  description: "Application-layer ArchiMate view"
  entity_search_filter: true
  diagram_only_types: []             # see "Diagram-only entity types" below
  type_ui_slots: {}
```

All fields except `name` are optional. Omitting a field uses the built-in default (empty lists, no grouping, no layout hints). `ontology` names the ontology package that supplies the base entity and connection vocabulary.

## Diagram-only entity types

Some diagram types own entity types that exist only within the diagram's `diagram-entities:` frontmatter — they are never written to the model entity store. Each such entity type is declared in two places:

- **`ontology.yaml`** — the authoritative source for all structural and semantic fields: element classes, properties, connection types, cardinality constraints, permitted mappings, and authoring guidance.
- **`config.yaml`** — UI metadata only: the display label and plural form.

### `config.yaml` entries (UI metadata only)

```yaml
ui:
  diagram_only_types:
    - entity_type: swimlane   # must match an entity_type declared in ontology.yaml
      label: Swimlane         # display label shown in the UI
      plural: Swimlanes       # plural form (for UI lists)
      include_in_global_search: false  # opt in only when useful outside its host diagram
```

The `config.yaml` entry contains the UI fields `entity_type`, `label`, `plural`, and the
optional `include_in_global_search` flag. The flag defaults to `false`: diagram-owned
constructs remain available in diagram pickers, but do not displace model entities in global
search unless a module explicitly opts them in. All structural fields (`min`, `max`,
`create_when`, `never_create_when`, `permitted_mappings`, `mapping_required`, `classes`,
`properties`, `required_connections`) belong in `ontology.yaml` and are merged at load time.

## `ontology.yaml` schema

Diagram types with custom entity types declare an `ontology.yaml` alongside `config.yaml`. This file is the authoritative source for diagram-owned entity types and connection types.

```yaml
connection_types:
  step-note-of:
    embedding: property        # "property": annotation entities embed their schema in host $defs
    embed_key: note            # the property name injected into the host's schema
    cascade_delete_source: true  # host deleted → annotation deleted

  swimlane-maps-to: {}         # plain reference connection; no structural effect

entity_types:
  swimlane:
    classes: [grouping]
    min: 2                     # minimum cardinality (0 = optional)
    max: null                  # maximum cardinality (null = unlimited)
    create_when: >-
      Represents one parallel track in the process.
    never_create_when: >-
      Do not create when the process has only one actor.
    permitted_mappings:
      entity_types: [role, business-actor, application-component]
      entity_classes: []
      sources:
        - ontology: archimate-4-0
          entity_type: role
          transparent: false
    mapping_required: false
    properties: {}

  action:
    classes: [control-flow, step]
    create_when: "Use for a single task performed by one actor in one lane."
    never_create_when: "Do not use for branching logic."
    required_connections:
      - connection_type: step-in-lane
        target: swimlane
        cardinality: [0, 1]
    properties:
      link: {type: string, required: false}

  note:
    classes: [annotation]
    required_connections:
      - connection_type: step-note-of
        target: "@step"       # @class-name or concrete entity type name
        cardinality: [1, 1]   # [min, max]; null max = unbounded
    properties:
      side: {type: string, enum: [left, right], required: false}
      text: {type: string, required: true}

permitted_relationships:
  - [swimlane, business-actor, [swimlane-maps-to]]
  - [swimlane, role,           [swimlane-maps-to]]
```

### `connection_types`

`embedding` values: `property` | `array` | `none` (default). When `embedding: property`, the annotation entity type's schema is injected as a named property (using `embed_key`) into the `$defs` of each host entity type in the generated diagram-entities schema. Connection types without `embedding` are plain reference connections.

### `entity_types`

| Field | Purpose |
|---|---|
| `classes` | Classification tags; control which diagram type filters include this type |
| `min` / `max` | Cardinality bounds across the whole diagram |
| `create_when` / `never_create_when` | AI and human authoring guidance |
| `permitted_mappings` | Which model entity types/classes this diagram entity may reference via `entity_id` |
| `mapping_required` | Whether a model-entity link is mandatory |
| `required_connections` | Mandatory connections; drives annotation schema injection |
| `properties` | Domain-specific JSON Schema fragments; `required: false` omits from `required` array |

`permitted_mappings.sources` is the extensible form for cross-ontology reuse. Each source entry names an ontology package plus either `entity_type` or `entity_class`. This is the preferred mechanism when a diagram-owned type can transparently reuse model entities from multiple ontologies.

### Diagram-entity array keys

Each entity type declared in `ontology.yaml` gets **its own top-level array in the diagram-entities**, keyed by the entity type name:

```yaml
# diagram-entities: frontmatter in a diagram artifact
diagram-entities:
  swimlane:
    - {id: sw-1, label: Customer}
    - {id: sw-2, label: System}
  action:
    - {id: a1, label: Submit}
    - {id: a2, label: Process}
  note:
    - {id: n1, text: Review required, side: right}
```

Structural relationships between diagram entities are **not** stored as properties on the entity. They are stored in `connections:` as a flat list of connection objects, parallel to `diagram-entities:`:

```yaml
# connections: frontmatter in a diagram artifact
connections:
  - id: kc-1
    conn_type: step-in-lane
    source: a1
    target: sw-1
  - id: kc-2
    conn_type: step-in-lane
    source: a2
    target: sw-2
  - id: kc-3
    conn_type: step-note-of
    source: n1
    target: a1
```

Each entry has `id` (unique within the diagram), `conn_type`, `source`, and `target` — all local IDs within `diagram-entities:`. At render time these are loaded as `ConnectionRecord` objects and passed to the renderer alongside the diagram's model-level connections. Renderers build lookup indexes (step→lane, step→note) from them.

`connections` entries exist only within the diagram file. They are never written to the model connection store and have no standalone artifact file.

### `$defs` in schemas

The schema generator produces one `$defs/<entity_type>` entry per entity type, built from its declared `properties`. For annotation types with `embedding: property`, the annotation's schema is additionally injected under `$defs/<host_entity_type>.properties.<embed_key>`.

### Element class declarations

Element classes must be declared in `config.yaml` under `element_classes:` before use in `ontology.yaml` (as `classes:`). Unknown class references abort startup validation.

## Element-class filter table

For ontology-bound domain views, `filter.hierarchy_level` selects entity types by a hierarchy segment. The common domain filter uses `index: 0`, which compares `EntityTypeInfo.hierarchy[0]` against the configured values. Only matching entity types are included in `effective_entity_types()` and shown in the entity picker.

| Domain | `filter.hierarchy_level.values` value |
|---|---|
| Motivation | `motivation` |
| Strategy | `strategy` |
| Business | `business` |
| Application | `application` |
| Technology | `technology` |
| Implementation | `implementation` |
| Common (cross-domain) | `common` |

The `archimate-layered` kind accepts all domains and therefore lists the full vocabulary.

## When a custom `renderer.py` is needed

The `GenericPumlRenderer` (in `src/infrastructure/rendering/generic_puml_renderer.py`) handles baseline config-backed PlantUML rendering. Standard ArchiMate views are layered on top of it through the shared `ArchimatePumlRenderer` in `src/infrastructure/rendering/archimate_puml_renderer.py`. You do **not** need a per-diagram-type custom renderer for:
- Any domain view (motivation, strategy, business, application, technology, implementation, layered)
- Views that add or remove hierarchy filter values
- Views with different `includes`, `grouping`, or `layout` settings

You **do** need a custom renderer (implementing the `DiagramRenderer` protocol) when:
- The diagram format is not PlantUML ArchiMate (e.g. ER diagrams, sequence diagrams, matrix tables)
- The rendering logic requires entity-specific logic that cannot be expressed via config
- You are building a diagram type for a non-ArchiMate ontology with its own notation
- The diagram type owns diagram-scoped state in `diagram-entities` that affects rendering, such as activity swimlanes

ArchiMate-specific note:
- The shared ArchiMate renderer is the correct place for ArchiMate-only behavior such as selective connection-label rendering from model connection data.
- Connection descriptions must remain hidden by default. Only explicit per-diagram opt-in metadata should surface connection description text or cardinalities.
- For ArchiMate diagrams, `diagram_connections` can be used as per-diagram connection annotation metadata keyed by model connection `artifact_id`. This metadata does not create diagram-owned connections. Supported keys are `artifact_id` (or `connection_id`), `include_description`, `include_cardinality`, and `label`.

The `matrix` diagram type is an example: it uses `_MatrixRenderer` that raises `ValueError` on `render_body` because matrix diagrams use a separate Markdown rendering path, not PlantUML. See `src/diagram_types/matrix/__init__.py`.

Custom renderers also own two extension hooks beyond `render_body(...)`:

- `inject_includes(body, repo_root)` adds stereotype marker includes if absent and rewrites them to selectively inline only the skinparam blocks and SVG sprites that the diagram actually uses. No external `_macros.puml` file is used. Activity and C4 renderers return the body unchanged.
- `collect_references(diagram_type, repo_root, *, diagram_entities, diagram_connections)` returns model `entity_ids` and `connection_ids` implied by diagram-owned data or annotation metadata. The shared write path persists those references into frontmatter without any diagram-type-specific branching.

Generic infrastructure must call these hooks through the renderer protocol. It must not inspect diagram type names to decide how to prepare or analyze a diagram.

## Adding a new diagram type

### Step 1 — Create the package directory

```
src/diagram_types/my_view/
  __init__.py
  config.yaml
```

### Step 2 — Write `config.yaml`

```yaml
name: my-view
filter:
  hierarchy_level:
    index: 0
    values: [application, technology]
includes: []
grouping:
  by_field: hierarchy_0
  stereotype_pattern: "{hierarchy_0|capitalize}Grouping"
layout:
  nesting_connection_classes: [nesting]
  flow_connection_classes: [dynamic]
guidance:
  when_to_use: "Use when ..."
  when_not_to_use: "Do not use when ..."
ui:
  label: "My View"
  description: "A concise label for the diagram type picker"
  entity_search_filter: true
  diagram_only_types: []
  type_ui_slots: {}
```

### Step 3 — Implement `__init__.py`

For standard ontology-bound ArchiMate views, re-use the ArchiMate-aware loader:

```python
# src/diagram_types/my_view/__init__.py
from __future__ import annotations

from pathlib import Path
from src.diagram_types.archimate._type import load_archimate_diagram_type
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule

module: DiagramTypeModule = load_archimate_diagram_type(Path(__file__).parent)
```

For a non-ArchiMate diagram-owned family with shared behavior, provide a custom loader instead. The built-in C4 packages use `load_c4_diagram_type(...)` in `c4/_type.py` as the reference pattern.

### Step 4 — Register the module

In `src/diagram_types/__init__.py`, add the import and register call:

```python
from src.diagram_types.my_view import module as my_view

def register_default_diagram_types(registry: ModuleRegistry) -> None:
    for module in [..., my_view]:
        registry.register_diagram_type(module)
```

### Step 5 — Verify

The protocol compliance test in `tests/domain/test_protocol_compliance.py` automatically checks every registered diagram type. Run `uv run pytest tests/` — the new kind must pass all checks without modification.

## Diagram-type-owned connection types

A diagram type can declare connection types that belong to it exclusively — types that are not defined in any ontology YAML but are globally queryable and validatable through the registry.

Declare them by overriding `own_connection_types` in the diagram type class:

```python
_MY_OWN_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {
    ConnectionTypeName("c4-uses"): ConnectionTypeInfo(
        artifact_type="c4-uses",
        conn_lang="c4",
        symmetric=False,
        puml_arrow="-->",
        classes=(),
        hierarchy_priority=None,
        hierarchy_label="uses",
    ),
}

@property
def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
    return _MY_OWN_CONNECTION_TYPES
```

`ModuleRegistry` merges `own_connection_types` from all registered diagram types into the global lookup:

- `registry.all_connection_types()` — includes all diagram-type-owned types
- `registry.find_connection_type(name)` — finds ontology and diagram-type-owned types
- `registry.connection_types_with_classification(cls)` — searches both sources

This ensures the write pipeline can validate and create connections of any diagram-type-owned type without the generic registry needing to know about diagram-specific concepts.

### `c4:` config block

C4 diagram types declare their scope and rendering semantics in `config.yaml`:

```yaml
c4:
  scope_entity_type: software-system   # entity type that acts as the scope
  scope_render_mode: boundary          # "boundary" = outer frame; "node" = regular node
  internal_entity_types:               # entity types rendered inside the scope boundary
    - container
```

`_C4DiagramType` reads this block in the renderer (to choose the outer boundary style).

## Protocol contract

Every diagram type must satisfy the `DiagramTypeModule` protocol (`src/domain/ontology_representation/ontology_protocol.py`). Compliance is verified automatically on every test run:

- `isinstance(module, DiagramTypeModule)` must return `True`
- `module.name` must equal the key under which the module is registered
- `effective_entity_types()` must only return types present in the global registry
- `effective_connection_types()` must only return types present in the global registry
- `accepts_entity_type(t)` must return `True` for every `t` in `effective_entity_types()`
- `accepts_connection_type(t)` must return `True` for every `t` in `effective_connection_types()`

## `ViewProjector` capability — model-backed view projection

Diagram types that derive their content from the ArchiMate graph may optionally implement the `ViewProjector` capability (`src/domain/viewpoints/view_projection.py`). C4 diagram types implement this.

```python
class ViewProjector(Protocol):
    def project_view(
        self,
        diagram_type: str,
        diagram_entities: Mapping[str, object],
        query: ModelQuery,
    ) -> ViewProjectionResult | None: ...
```

`project_view` runs **one** engine call and returns both:
- `result.derivation` — normalized `ViewDerivation` (strategy name, params, snapshot, selection) for persistence and the refresh/diff path (Seam B).
- `result.items` — classified `ProjectedViewItem` list for the preview checklist (Seam C).

The generic preview service (`src/application/derivation/preview.py`) discovers `ViewProjector` at runtime via `isinstance` and stays diagram-type-agnostic: it forwards `display_class` and `role` as opaque strings. Selection (include/exclude) is applied at the generic layer from the normalized `DerivationSelection`, never from C4-specific keys.

### Single-engine pattern (C4)

`src/diagram_types/c4/_projection.py` is the **one** C4 projection algorithm. Both the preview path (`project_view → to_view_items()`) and the refresh/diff path (registered `c4.scope-projection` strategy → `to_candidate_set()`) are produced from a single `project_c4(...)` call. The renderer (`c4/_resolve._resolve_model_backed`) also calls `project_c4`, so preview and render are structurally identical.

Registration (Seam B) runs as a module-level side effect when `c4/_projection.py` is imported. This happens automatically when any C4 diagram-type package loads (via `c4/_type.py`). Generic code never names C4 concepts.
