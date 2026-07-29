---
name: ontology-module-scaffold
description: >
  Scaffold a new ontology module under src/ontologies/<name>/ and wire it into the
  module registry. Use this when the user wants to add a new base ontology (e.g. a new
  ArchiMate snapshot or a domain-specific element vocabulary). Trigger on phrases like
  "new ontology module", "scaffold ontology", "add an ontology", or "create a <X> ontology".
---

# Ontology Module Scaffold

Gather the following before creating any files. Ask all at once if not already provided:

1. **Module name** — snake_case directory name (e.g. `archimate_4`, `domain_v2`).
2. **Display name** — human-readable name used in the `OntologyModule.name` property.
3. **Entity types** — list of entity types to define, each with: `prefix`, `hierarchy` path, `element_classes`, `create_when`, `never_create_when`.
4. **Element classes** — abstract classification classes used by entity types (e.g. `motivation-element`, `active-structure-element`).
5. **Connection types** — connection types with `puml_arrow`, `symmetric`, `classifications`, and any ArchiMate relationship metadata.
6. **Permitted relationships** — rules as `[source, target, [conn-short-names]]`. May use `@all`, `@same`, or `@<class>` references.

---

## Files to Create

### 1. `src/ontologies/<name>/entities.yaml`

```yaml
# Entity Ontology — <Display Name> entity type definitions

element_classes:
  <class-name>:
    description: <description>

entity_types:
  <entity-type>:
    prefix: <PREFIX>
    hierarchy:
      - <domain>
      - <subdomain>
    element_classes: [<class-name>]
    create_when: >-
      <when to model something as this type>
    never_create_when: >-
      <when not to model something as this type>
```

### 2. `src/ontologies/<name>/connections.yaml`

```yaml
# Connection Ontology — <Display Name> connection types & relationship rules

connection_types:
  archimate:  # or a custom section key
    <conn-short-name>:
      archimate_relationship_type: <Type>
      puml_arrow: "-->"
      symmetric: false
      classifications: []

permitted_relationships:
  - [<source>, <target>, [<conn-short-name>]]
```

### 3. `src/ontologies/<name>/_loader.py`

Model after `src/ontologies/archimate_4/_loader.py`:
- Load `entities.yaml` and `connections.yaml` with `yaml.safe_load`
- Parse `element_classes`, `entity_types`, `connection_types`, and `permitted_relationships`
- Build and return an `OntologyModule`-compatible object

### 4. `src/ontologies/<name>/__init__.py`

```python
"""<Display Name> ontology module."""

from pathlib import Path
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.<name>._loader import load_<name>_module

_mod = load_<name>_module(Path(__file__).parent)
module: OntologyModule = _mod
```

---

## Registration

### 5. `src/application/app_bootstrap.py`

Add the import and register the ontology before diagram types:
```python
from src.ontologies.<name> import module as <name>_module

def build_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_ontology(archimate_4_module)
    registry.register_ontology(<name>_module)  # add here
    register_default_diagram_types(registry)
    return registry
```

---

## Verification

```bash
uv run pytest tests/ -q
uv run ruff check src/ontologies/<name>/
uv run zuban check src/
```

Add a smoke test confirming the ontology loads and key entity types are present:
```python
def test_<name>_ontology_loads() -> None:
    from src.ontologies.<name> import module
    assert module.name == "<display-name>"
    assert "<entity-type>" in {str(et) for et in module.entity_types}
```
