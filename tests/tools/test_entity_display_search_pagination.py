"""Domain/entity-type filters + cursor pagination for GET /api/entity-display-search.

Reproduces WU-A1 symptom 2 (application-domain entities truncated off an unfiltered first
page) and verifies the cursor walk is exhaustive and non-duplicating, and that a
diagram-type filter composes correctly with a domain filter.
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(
    artifact_id: str,
    name: str,
    *,
    artifact_type: str = "requirement",
    yaml_domain: str = "Motivation",
    element_type: str = "Requirement",
) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Test entity for entity-display-search pagination.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: {yaml_domain}
element-type: {element_type}
label: "{name}"
alias: e_{slug}
```
"""


@pytest.fixture()
def paginated_entities_root(tmp_path: Path) -> Path:
    """Several motivation-domain entities (sort first) plus one application-domain entity
    (sorts after) — reproduces symptom 2: an unfiltered small-limit page omits the
    application entity, but a domain filter surfaces it directly.
    """
    root = tmp_path / "engagements" / "ENG-PAGE" / "architecture-repository"
    motivation_dir = root / "model" / "motivation" / "requirement"
    application_dir = root / "model" / "application" / "application-component"
    for i in range(4):
        artifact_id = f"REQ@1000000030.Page.motivation-{i}"
        _write(motivation_dir / f"{artifact_id}.md", _entity_md(artifact_id, f"Motivation Entity {i}"))
    app_id = "APP@1000000030.Page.application-entity"
    _write(
        application_dir / f"{app_id}.md",
        _entity_md(
            app_id, "Application Entity",
            artifact_type="application-component", yaml_domain="Application", element_type="ApplicationComponent",
        ),
    )
    return root


@pytest.fixture()
def paginated_client(paginated_entities_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    repo = ArtifactRepository(shared_artifact_index([paginated_entities_root]))
    gui_state.init_state(repo, paginated_entities_root, None)
    app = FastAPI()
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    app.include_router(diagrams_router)
    return TestClient(app)


class TestEntityDisplaySearchPaginationAndFilters:
    def test_unfiltered_small_page_omits_application_entity(self, paginated_client) -> None:
        r = paginated_client.get("/api/entity-display-search?q=&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert all(item["domain"] == "motivation" for item in body["items"])
        assert body["next_cursor"] is not None

    def test_domain_filter_surfaces_application_entity(self, paginated_client) -> None:
        r = paginated_client.get("/api/entity-display-search?q=&limit=2&domains=application")
        assert r.status_code == 200
        body = r.json()
        assert [item["domain"] for item in body["items"]] == ["application"]
        assert body["next_cursor"] is None

    def test_cursor_walk_yields_all_entities_exactly_once(self, paginated_client) -> None:
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(10):
            url = "/api/entity-display-search?q=&limit=2" + (f"&cursor={cursor}" if cursor else "")
            body = paginated_client.get(url).json()
            seen.extend(item["artifact_id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert len(seen) == len(set(seen)), "cursor walk must not duplicate entities"
        assert len(seen) == 5, "cursor walk must reach every entity (4 motivation + 1 application)"

    def test_diagram_type_and_domain_filters_compose(self, paginated_client) -> None:
        r = paginated_client.get(
            "/api/entity-display-search?q=&diagram_type=archimate-application&domains=motivation"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == [], "motivation domain has no entity types accepted by an application diagram"
