# Ontology Modules

Each subdirectory is a self-contained *ontology module* — a pluggable vocabulary of entity types, connection types, and permitted relationship rules. The system loads all registered modules at startup and merges them into the global `ModuleRegistry`.

## How it fits together

```
src/ontologies/
  archimate_4/     ← shipped module
  <your-ontology>/    ← your module here
  __init__.py

src/infrastructure/app_bootstrap.py   ← register modules here
src/domain/ontology_representation/ontology_protocol.py       ← OntologyModule protocol definition
src/domain/modules/module_registry.py         ← ModuleRegistry class
```

## Adding a new ontology module

### Step 1 — Create the package directory

```
src/ontologies/my_ontology/
  __init__.py
  entities.yaml
  connections.yaml        (optional — only if the ontology defines connection types)
  relationship_derivation.yaml  (optional — indirect-relationship rules)
  _loader.py              (optional — use the archimate_4 loader as a template)
```

### Step 2 — Define entity types in `entities.yaml`

```yaml
# entities.yaml
entity_types:
  part-definition:
    prefix: PDF
    hierarchy: [my-domain]
    classes: [definition, structure-element]
    create_when: "Create a part-definition to model a structural type."
    never_create_when: "Don't use for behavioural elements; use action-definition instead."

  action-definition:
    prefix: ADF
    hierarchy: [my-domain]
    classes: [definition, behavior-element]
    create_when: "Create an action-definition to model a behavioral type."
    never_create_when: ""
```

Required fields for each entity type:

| Field | Type | Purpose |
|---|---|---|
| `prefix` | string | Short uppercase prefix used in generated artifact IDs (e.g. `PDF@...`) |
| `hierarchy` | list of strings | Domain path segments under `model/`; `hierarchy[0]` is the grouping domain used by the frontend and filters |
| `classes` | list of strings | Element classes used by diagram type filters and connection rules |
| `create_when` | string | Agent/user guidance — when to create this type |
| `never_create_when` | string | Agent/user guidance — when not to create this type |

The special `internal: true` flag marks an entity type as system-managed (e.g. `global-artifact-reference`). Internal types are excluded from all user-facing type catalogs and domain listings.

**Frontend domain chip convention:** every new `hierarchy[0]` domain name introduced by an ontology module **must** have a display entry added to `tools/gui/src/ui/lib/domains.ts` under `DOMAIN_CONFIG`. Without it the domain chip renders with a fallback grey and the raw domain string. The entry format is:

```typescript
my_domain: { color: '#rrggbb', label: 'Human-Readable Name' },
```

The domain name in `DOMAIN_CONFIG` must exactly match the string used as `hierarchy[0]` in `entities.yaml` (and as emitted in `DOMAIN_NAMES` in `types.generated.ts`). Choose a colour that is visually distinct from the existing ArchiMate domain colours (motivation `#d8c1e4`, strategy `#efbd5d`, common `#e8e5d3`, business `#f4de7f`, application `#b6d7e1`, technology `#c3e1b4`, implementation `#f4c896`).

### Step 3 — Define connection types and rules in `connections.yaml` (optional)

```yaml
# connections.yaml
connection_types:
  my-connects:
    conn_lang: sysml
    archimate_relationship_type: ~
    puml_arrow: "-->"
    symmetric: false
    classes: [flow]

permitted_relationships:
  - [block, block, [my-connects]]
  - [block, activity, [my-connects]]
  - ["@behavior-element", "@structure-element", [my-connects]]
```

The source/target columns accept:
- A literal entity type name: `block`
- `@<class>` — all entity types with that `classes` entry
- `@all` — every entity type in this ontology
- A list: `[block, activity]` — union of the listed types/classes
- `@same` — the same entity type as the source (for self-referential rules)

### Step 4 — Implement the module object

The simplest implementation uses a loader that produces an `OntologyModule`-compatible object:

```python
# src/ontologies/my_ontology/__init__.py
from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

class _MyOntologyModule:
    name = "my-ontology"

    def __init__(
        self,
        entity_types: dict[EntityTypeName, EntityTypeInfo],
        connection_types: dict[ConnectionTypeName, ConnectionTypeInfo],
        permitted: PermittedRelationshipSet,
    ) -> None:
        self._entity_types = entity_types
        self._connection_types = connection_types
        self._permitted = permitted

    @property
    def entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._entity_types

    @property
    def connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return self._permitted

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset(n for n, info in self._entity_types.items() if cls in info.classes)

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return frozenset(
            n for n, info in self._connection_types.items()
            if cls in info.classes
        )

    def permits_connection(
        self, src: EntityTypeName, tgt: EntityTypeName, conn: ConnectionTypeName
    ) -> bool:
        return self._permitted.permits(src, tgt, conn)


# Load at import time so `from src.ontologies.my_ontology import module` works
# (same pattern as archimate_4)
def _load() -> _MyOntologyModule:
    # parse entities.yaml, connections.yaml → build entity_types, connection_types, permitted
    # see src/ontologies/archimate_4/_loader.py for a full example
    ...

module = _load()
```

See `src/ontologies/archimate_4/_loader.py` for a complete loader implementation including YAML parsing, `@class` expansion, and `permitted_relationships` rule processing.

### Optional: define indirect-relationship rules declaratively

An ontology can add `relationship_derivation.yaml`. Every registered ontology exposes
`derivation_rules`; modules without this file expose an empty tuple. The evaluator receives
these rules from the module rather than containing ontology-specific rule tables in Python.

```yaml
composition_rules:
  - spec_ref: MY-1
    certainty: certain
    first_role: structural
    second_role: dependency
    result: second
    join: target-source
    result_source: first-source
    result_target: second-target
```

`first_role` and `second_role` match the ontology's connection derivation roles. `result`
selects `first`, `second`, `weakest`, `specialization`, `triggering`, or `flow`; the optional
join and endpoint fields describe how the two stored relationships are oriented.

### Step 5 — Register the module

In `src/infrastructure/app_bootstrap.py`:

```python
from src.ontologies.my_ontology import module as my_ontology_module

def build_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_ontology(archimate_4_module)
    registry.register_ontology(my_ontology_module)   # ← add this line
    register_default_diagram_types(registry)
    return registry
```

The registry merges all ontologies: `registry.all_entity_types()` returns the union of every registered ontology's entity vocabulary. Type names must be globally unique across all registered ontologies.

### Step 6 — Add a diagram type (optional)

If the new ontology needs a purpose-built diagram view, add a diagram type package under `src/diagram_types/`. See `src/diagram_types/README.md` for the extension contract.

## Cross-ontology connection rules and ownership

Connection rules are globally unique: entity type names must not collide across registered ontologies (enforced at startup). This means an ArchiMate `permitted_relationships` rule referencing a `business-actor` source unambiguously identifies the same type regardless of which ontology contributed it.

Cross-ontology reuse inside diagram types is handled separately from canonical model ownership. Diagram-owned entity types may declare `permitted_mappings.sources` to transparently reuse model entity types or element classes from one or more ontologies. Keep those mappings in the diagram type module rather than duplicating canonical entity types across ontologies.

Connections fall into two ownership categories:

| Category | Who declares the rule | Who owns the connection instance |
|---|---|---|
| **Model-to-model** | `permitted_relationships` in any `OntologyModule` | The model; stored as `ConnectionRecord` in the model store |
| **Diagram-owned** | `permitted_connections` on a `DiagramOwnEntityTypeUiConfig` | The diagram; stored in `diagram-entities:` frontmatter |

A connection between two model entity types is always model-owned. A connection that involves at least one diagram-only entity type (a type declared in `diagram_only_types` of some diagram type) must be declared as a diagram-owned rule. Use `ModuleRegistry.is_diagram_entity_type(name)` to classify a type at runtime.

`DiagramKindBase.effective_permitted_relationships` automatically merges:
1. Ontology `permitted_relationships` filtered to accepted entity/connection types
2. The diagram type's `own_permitted_relationships`
3. All `permitted_connections` rules from every `diagram_only_types` entry

## Protocol contract

Every ontology module must satisfy the `OntologyModule` protocol defined in `src/domain/ontology_representation/ontology_protocol.py` (it is `@runtime_checkable`). The protocol compliance test suite in `tests/domain/test_protocol_compliance.py` verifies all registered modules on every CI run:

- `isinstance(module, OntologyModule)` must return `True`
- `permitted_relationships._rules` must only reference entity type names present in `entity_types`
- `permitted_relationships._rules` must only reference connection type names present in `connection_types`
- `entity_types_with_class(cls)` must return a subset of `entity_types`

## Required connections and owned entity types

`EntityTypeInfo` supports a `required_connections` field (tuple of `RequiredConnection`). This is primarily used by diagram types for annotation/owned entity types (e.g. `note` entities that must always be attached to a host step). Non-ArchiMate model ontologies with owned member entities (class diagrams, SysML block-and-part diagrams) may also use `required_connections` to declare mandatory structural relationships.

`RequiredConnection` fields:
- `connection_type` — name of the connection type
- `target` — entity type name or `@class-name` reference
- `cardinality_min`, `cardinality_max` — bounds (`None` max = unbounded)

For diagram types, `required_connections` on diagram-owned entity types drives annotation schema injection: when a connection type has `embedding: property`, the annotation entity's schema is injected as a named property (under `embed_key`) into the `$defs` of each matching host entity type in the generated diagram-entities JSON Schema.

At runtime, note→step relationships are stored as `ConnectionRecord` objects (with the declared `conn_type`), not as properties on the note entity. Renderers receive the `connections` sequence alongside `diagram-entities` and build a step-id → note index from connections of the relevant type.

## Element class declarations

Each element class must be declared by **exactly one** registered module. A module may freely *reference* element classes declared by other modules; it must **not redeclare** them. `ModuleRegistry.all_element_classes()` raises `ValueError` on any duplicate declaration, and startup validation aborts with an "Element class declaration conflict" error.

Model ontologies declare their own classes in `entities.yaml` under a top-level `element_classes:` block:

```yaml
element_classes:
  structure-element:
    description: Static structural element (ArchiMate)
  behavior-element:
    description: Dynamic/behavioral element (ArchiMate)
```

Diagram types declare their element classes in `config.yaml` under `element_classes:`. To reuse a class from another module, simply list it in `classes:` without redeclaring it:

```yaml
# OK — sysml_v2_min reuses classes owned by archimate_4
entity_types:
  part-definition:
    classes: [definition, structure-element]   # 'definition' declared here; 'structure-element' from archimate_4
```

## Multi-module conventions

Follow these rules when adding any new ontology module alongside an existing one:

**1. Domain name uniqueness.** Each ontology module must use a distinct `hierarchy[0]` domain name not used by any other module. Reusing another module's domain name mixes types from different ontologies into the same frontend group and makes `hierarchy[0]`-based filtering unreliable.

**2. Element class ownership.** Declare only the element classes that belong to your module's vocabulary. If your entity types need a class already declared by another module, reference it directly in `classes:` — do not redeclare it. Startup validation enforces this by aborting on any duplicate.

**3. Frontend domain chip.** Every new `hierarchy[0]` domain name must have a corresponding entry in `tools/gui/src/ui/lib/domains.ts` under `DOMAIN_CONFIG` (see the convention note in Step 2 above). Omitting it causes the domain chip to render with a fallback grey and the raw string.

**4. Type name uniqueness.** Entity type names and connection type names must be globally unique across all registered ontologies (`ModuleRegistry` enforces this at startup with a `ValueError`).

## Startup validation

At backend startup, `src/application/startup_validation.py` compares every entity type, connection type, and diagram type found in indexed repo content against the registered modules. Startup is aborted if any unsupported type is found, with a report listing each unknown type and an example artifact ID. This prevents silent data corruption when an ontology module is removed or renamed while repos still contain artifacts of that type.

The validator also checks element class declarations: every `classes` value on every registered entity type and diagram-only entity type must be present in `registry.all_element_classes()`. Unknown class references are reported as errors.
