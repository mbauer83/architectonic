"""The composition-root closure for the ``viewpoint_execution`` strategy: proves
``params["repo_roots"]`` threading actually resolves a real catalog/registries/read-access
against a fixture repo on disk, registered exactly as ``app_bootstrap.py`` wires it."""

from __future__ import annotations

from pathlib import Path

from src.application.derivation.strategy_registry import DerivationStrategyCatalogBuilder
from src.application.derivation.viewpoint_execution import SPEC
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.derivation_strategy_wiring import viewpoint_execution_derive


def _entity_md(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: application-component
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Entity for derivation-strategy-wiring testing.

## Properties

| Attribute | Value |
|---|---|

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: Application Component
label: "{name}"
alias: AC_{artifact_id.split(".")[-1].replace("-", "_")}
```
"""


def test_viewpoint_execution_derive_resolves_catalog_from_params_repo_roots(tmp_path: Path) -> None:
    root = tmp_path / "engagements" / "ENG-DSW" / "architecture-repository"
    entity_id = "ARC@1000000000.EntDsw.wiring-entity"
    path = root / "model" / "application" / "application-component" / f"{entity_id}.md"
    path.parent.mkdir(parents=True)
    path.write_text(_entity_md(entity_id, "Wiring Entity"), encoding="utf-8")

    builder = DerivationStrategyCatalogBuilder()
    builder.register(SPEC, viewpoint_execution_derive)
    catalog = builder.build()

    derive_fn = catalog.lookup_derive_fn(SPEC.name, SPEC.version)
    assert derive_fn is not None

    query_index = shared_artifact_index([root])
    candidates = derive_fn(
        {"query": {}, "repo_roots": [str(root)]},
        SourceModelSnapshot(repo_scope="both"),
        query_index,
    )
    assert entity_id in candidates.entity_ids
