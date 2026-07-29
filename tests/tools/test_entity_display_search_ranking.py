"""Model-vs-diagram-owned ranking for GET /api/entity-display-search.

Diagram-owned constructs (C4 persons, swimlanes, …) are legitimately searchable, but they
must never outrank real model entities in a picker, and every item must carry the
``diagram_internal`` flag so the GUI can render the partition divider.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.diagrams import router as diagrams_router

httpx = pytest.importorskip("httpx")

_SYSTEM_ID = "APP@1000000031.Rank.ordering-backend"
_DIAGRAM_ID = "DGM@1000000031.Rank.ordering-context"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_SYSTEM_CONTENT = f"""\
---
artifact-id: {_SYSTEM_ID}
artifact-type: application-component
name: "Ordering Backend"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Ordering Backend

The backend component processing orders.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: ApplicationComponent
label: "Ordering Backend"
alias: app_ordering_backend
```
"""

_C4_DIAGRAM_CONTENT = f"""\
---
artifact-id: {_DIAGRAM_ID}
artifact-type: diagram
name: Ordering Context
version: 0.1.0
status: draft
diagram-type: c4-system-context
entity-ids-used:
  - {_SYSTEM_ID}
diagram-entities:
  person:
    - id: ordering-clerk
      label: Ordering Clerk
      description: Places orders in the backend
  software-system:
    - id: ordering
      label: Ordering Backend
      entity_id: {_SYSTEM_ID}
      scope: true
      description: Processes customer orders
last-updated: '2026-01-01'
---
@startuml ordering-context
title Ordering Context
actor "Ordering Clerk" as ACT_Clerk1
rectangle "Ordering Backend" <<C4System>> as APP_Order1
ACT_Clerk1 --> APP_Order1 : Uses
@enduml
"""


@pytest.fixture()
def ranking_client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    root = tmp_path / "engagements" / "ENG-RANK" / "architecture-repository"
    _write(root / "model" / "application" / "application-component" / f"{_SYSTEM_ID}.md", _SYSTEM_CONTENT)
    _write(root / "diagram-catalog" / "diagrams" / f"{_DIAGRAM_ID}.puml", _C4_DIAGRAM_CONTENT)
    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    app.include_router(diagrams_router)
    return TestClient(app)


class TestModelEntitiesRankAboveDiagramConstructs:
    def test_query_search_partitions_model_entities_first_with_flag(self, ranking_client) -> None:
        body = ranking_client.get("/api/entity-display-search?q=ordering&limit=20").json()
        ids = [item["artifact_id"] for item in body["items"]]
        assert _SYSTEM_ID in ids
        flags = [item["diagram_internal"] for item in body["items"]]
        assert flags[0] is False, "a model entity must rank first"
        assert True in flags, "the diagram-owned construct must still be present, flagged"
        first_internal = flags.index(True)
        assert all(flag for flag in flags[first_internal:]), (
            "diagram-owned constructs must form one trailing partition, never interleave"
        )

    def test_browse_listing_sorts_model_entities_first(self, ranking_client) -> None:
        body = ranking_client.get("/api/entity-display-search?q=&limit=50").json()
        flags = [item["diagram_internal"] for item in body["items"]]
        assert flags[0] is False
        assert True in flags
        assert flags == sorted(flags)
