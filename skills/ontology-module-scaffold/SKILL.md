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
3. **Entity types** — list of entity types to define, each with: `prefix`, `hierarchy` path, `classes`, `create_when`, `never_create_when`.
4. **Element classes** — abstract classification classes used by entity types (e.g. `motivation-element`, `active-structure-element`).
5. **Connection types** — connection types with `puml_arrow`, `symmetric`, `classes`, and any ArchiMate relationship metadata.
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
    classes: [<class-name>]
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
      classes: []

permitted_relationships:
  - [<source>, <target>, [<conn-short-name>]]
```

### 3. `src/ontologies/<name>/_loader.py`

Model after `src/ontologies/sysml_v2_min/_loader.py` (the smallest shipped loader):
- Load `entities.yaml` and `connections.yaml` with `parse_yaml` from `src.domain.yaml_documents`,
  the project's one YAML reader — never `yaml.safe_load`
- Parse `element_classes`, `entity_types`, `connection_types`, and `permitted_relationships`
- Build and return an `OntologyModule`-compatible object

### 4. `src/ontologies/<name>/__init__.py`

```python
"""<Display Name> ontology module."""

from pathlib import Path
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.ontologies.<name>._loader import load_<name>_module

module: OntologyModule = load_<name>_module(Path(__file__).parent)
```

---

## Registration

### 5. `src/infrastructure/app_bootstrap.py`

Each shipped module is loaded once at import time and listed in `_ALL_ONTOLOGY_MODULES`;
`build_module_registry` registers every enabled module from that tuple. Load the new module
beside the others and add it to the tuple:

```python
from src.ontologies.<name>._loader import _PACKAGE_DIR as _<NAME>_PACKAGE_DIR
from src.ontologies.<name>._loader import load_<name>_module

_<name>_module = load_<name>_module(_<NAME>_PACKAGE_DIR)

_ALL_ONTOLOGY_MODULES = (
    _archimate_4_module, _sysml_v2_min_module, _assurance_module, _<name>_module,
)
```

Each loader module defines `_PACKAGE_DIR = Path(__file__).parent`. A loader that accepts a
`guidance` overlay is passed `_load_guidance_overlay(<alias>)`, as the shipped modules are.

---

## Verification

```bash
uv run pytest <the new test file> -q
uv run ruff check src/ tests/
uv run zuban check
uv run tools/ontology/generate_types.py   # then commit tools/gui/src/domain/types.generated.ts
```

Add a smoke test confirming the ontology loads and key entity types are present:
```python
def test_<name>_ontology_loads() -> None:
    from src.ontologies.<name> import module
    assert module.name == "<display-name>"
    assert "<entity-type>" in {str(et) for et in module.entity_types}
```
