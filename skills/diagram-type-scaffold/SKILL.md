---
name: diagram-type-scaffold
description: >
  Scaffold a new diagram type module under src/diagram_types/<name>/ and wire it into
  the registry. Use this when the user wants to add a new diagram type to the system.
  Trigger on phrases like "new diagram type", "add a diagram type", "scaffold diagram",
  or "create a <X> diagram type".
---

# Diagram Type Scaffold

Gather the following before creating any files. Ask all at once if not already provided:

1. **Diagram type name** — kebab-case identifier used in the registry (e.g. `sequence`, `data-flow`).
2. **Display label** — human-readable name for the UI (e.g. `Sequence Diagram`).
3. **Scope entity type** — the entity type that acts as the scope/root, if any (leave blank for free-form types like `activity`).
4. **Internal entity types** — list of entity types rendered inside the scope boundary (may be empty).
5. **Own entity types** — the diagram-only entity types this diagram owns (label, plural, `create_when`).
6. **Own connection types** — diagram-owned connection types, if any.
7. **entity_search_filter** — `true` if users pick ArchiMate model entities; `false` if the diagram manages its own entities via a config panel (default: `false` for diagram-owned types, `true` for model-backed ArchiMate diagrams).
8. **Renderer** — does this type need a custom `renderer.py`, or can it reuse an existing renderer? If reusing, which one?

---

## Files to Create

### 1. `src/diagram_types/<name>/ontology.yaml`

```yaml
connection_types:
  # diagram-owned connections (omit section if none)
  <conn-type>:
    embedding: none
    cascade_delete_source: false

entity_types:
  <entity-type>:
    element_classes: []
    min: 0
    create_when: >-
      <when to create this entity type>
    never_create_when: >-
      <when not to create this entity type>

permitted_relationships:
  - [<source-type>, <target-type>, [<conn-type>]]
```

### 2. `src/diagram_types/<name>/config.yaml`

```yaml
name: <name>

guidance:
  when_to_use: >-
    <one paragraph — when to use this diagram type>
  when_not_to_use: >-
    <one paragraph — when not to use it>

ui:
  label: <Display Label>
  description: <one-line description for the UI>
  entity_search_filter: false
  diagram_only_types:
    - entity_type: <entity-type>
      label: <Label>
      plural: <Labels>
```

### 3. `src/diagram_types/<name>/__init__.py`

Copy the pattern from `src/diagram_types/activity/__init__.py`:
- Import the renderer class
- Define `_OWN_ENTITY_TYPES` and `_OWN_CONNECTION_TYPES` (empty dicts if none)
- Define the `_<Name>DiagramType(DiagramTypeBase)` class
- Wire `_config`, `_ontology`, and the exported `module: DiagramTypeModule`

Key points:
- `primary_ontology` returns `FreeOntology` for diagram-owned types; returns the ArchiMate ontology for ArchiMate-backed types
- `accepts_entity_type` / `accepts_connection_type` return `False` for free types; delegate to ontology for ArchiMate types
- `own_permitted_relationships` returns `self._ontology.permitted_relationships`

### 4. `src/diagram_types/<name>/renderer.py` (if custom renderer needed)

Implement a class with:
```python
class <Name>PumlRenderer:
    def render_body(self, name, entities, connections, diagram_type, repo_root, *, diagram_entities=None, diagram_connections=None) -> str: ...
    def collect_references(self, diagram_type, repo_root, *, diagram_entities=None, diagram_connections=None) -> DiagramRendererReferences: ...
```

---

## Registration

### 5. `src/diagram_types/__init__.py`

Add the import and include in `DEFAULT_DIAGRAM_KINDS`:
```python
from src.diagram_types.<name> import module as <name_snake>
# ... add <name_snake> to DEFAULT_DIAGRAM_KINDS tuple
```

---

## Verification

After creating all files, run:
```bash
uv run pytest tests/tools/test_diagram_type_routes.py -q
uv run ruff check src/diagram_types/<name>/
uv run zuban check src/
```

Add a test in `tests/tools/test_diagram_type_routes.py` following the pattern:
```python
def test_default_registry_registers_<name>_diagram_type() -> None:
    registry = build_module_registry()
    dt = registry.find_diagram_type("<name>")
    assert dt is not None
    assert dt.ui_config.label == "<Display Label>"
```
