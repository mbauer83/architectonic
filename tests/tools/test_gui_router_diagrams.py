"""Tests for the GUI diagrams router.

Covers: GET /api/diagrams, /api/diagrams/{artifact_id} (404 + found), /api/entity-display-search,
the diagram-type member reads, /api/diagrams/{artifact_id}/context, /api/candidate-connections;
helper _rendered_name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams import router as diagrams_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Test entity for diagrams router.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{slug}
```
"""


def _diagram_md(
    artifact_id: str, name: str, diagram_type: str = "archimate-application", *, extra_frontmatter: str = ""
) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: {diagram_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
{extra_frontmatter}---
@startuml
component "Comp A" as compA
@enduml
"""


# ── IDs used across tests ─────────────────────────────────────────────────────

ENT_ID = "REQ@1000000020.EntDia.entity-for-diag"
DIAG_ID = "DIAG@1000000020.DiagTst.test-diagram"
ASSURANCE_DIAG_ID = "DIAG@1000000021.BowTest.legacy-bowtie"
GSN_DIAG_ID = "GSN@1000000022.GsnTst.selectable-gsn"
VIEWPOINT_DIAG_ID = "DIAG@1000000023.VptTst.viewpoint-applied"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-DIAG" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "requirement"
    diag_dir = root / "diagram-catalog" / "diagrams"
    _write(model_dir / f"{ENT_ID}.md", _entity_md(ENT_ID, "Entity For Diag"))
    _write(diag_dir / f"{DIAG_ID}.md", _diagram_md(DIAG_ID, "Test Diagram"))
    _write(
        diag_dir / f"{ASSURANCE_DIAG_ID}.md",
        _diagram_md(ASSURANCE_DIAG_ID, "Legacy Bowtie", "bowtie"),
    )
    _write(
        diag_dir / f"{VIEWPOINT_DIAG_ID}.md",
        _diagram_md(
            VIEWPOINT_DIAG_ID, "Viewpoint Applied",
            extra_frontmatter="viewpoint: {slug: motivation, version: 1}\n",
        ),
    )
    _write(
        diag_dir / f"{GSN_DIAG_ID}.puml",
        f"""\
---
artifact-id: {GSN_DIAG_ID}
artifact-type: diagram
diagram-type: gsn
name: "Selectable GSN"
version: 0.1.0
status: draft
last-updated: '2026-06-21'
diagram-entities:
  nodes:
    - node_id: g1
      name: Claim
      gsn_type: goal
    - node_id: s1
      name: Argument
      gsn_type: strategy
  edges:
    - source_id: g1
      target_id: s1
      conn_type: supported-by
---
@startuml
$GsnGoal(g1, "G: Claim")
$GsnStrategy(s1, "S: Argument")
$GsnSupportedBy(g1, s1)
@enduml
""",
    )
    return root


@pytest.fixture()
def sync_client(populated_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = build_api_app(diagrams_router)
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    return TestClient(app)


# ── GET /api/diagrams ─────────────────────────────────────────────────────────


class TestListDiagrams:
    def test_returns_total_and_items(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "items" in data

    def test_lists_created_diagram(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams")
        assert r.status_code == 200
        ids = [d["artifact_id"] for d in r.json()["items"]]
        assert DIAG_ID in ids

    def test_assurance_surface_diagrams_are_absent(self, sync_client) -> None:
        data = sync_client.get("/api/diagrams").json()
        assert ASSURANCE_DIAG_ID not in {d["artifact_id"] for d in data["items"]}
        filtered = sync_client.get("/api/diagrams?diagram_type=bowtie").json()
        assert filtered == {"total": 0, "items": []}

    def test_filter_by_type(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams?diagram_type=archimate-application")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_filter_by_type_no_match(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams?diagram_type=no-such-type")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_filter_by_status(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams?status=draft")
        assert r.status_code == 200
        assert r.json()["total"] >= 1


# ── GET /api/diagrams/{artifact_id} ──────────────────────────────────────────


class TestReadDiagram:
    def test_found(self, sync_client) -> None:
        r = sync_client.get(f"/api/diagrams/{DIAG_ID}")
        assert r.status_code == 200
        data = r.json()
        assert data["artifact_id"] == DIAG_ID

    def test_not_found_returns_404(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams/DIAG@9.ZZZ.no-such")
        assert r.status_code == 404

    def test_result_includes_diagram_fields(self, sync_client) -> None:
        r = sync_client.get(f"/api/diagrams/{DIAG_ID}")
        assert r.status_code == 200
        data = r.json()
        assert "name" in data
        assert "diagram_type" in data

    def test_viewpoint_is_absent_when_not_applied(self, sync_client) -> None:
        # Absent, not null: this read omits what is not set, so a diagram pinning no viewpoint
        # simply does not carry the key.
        r = sync_client.get(f"/api/diagrams/{DIAG_ID}")
        assert r.status_code == 200
        assert "viewpoint" not in r.json()

    def test_viewpoint_surfaces_when_applied(self, sync_client) -> None:
        r = sync_client.get(f"/api/diagrams/{VIEWPOINT_DIAG_ID}")
        assert r.status_code == 200
        assert r.json()["viewpoint"] == {"slug": "motivation", "version": 1}


def test_gsn_context_includes_selectable_diagram_owned_nodes_and_edges(sync_client) -> None:
    response = sync_client.get(f"/api/diagrams/{GSN_DIAG_ID}/context")
    assert response.status_code == 200
    body = response.json()
    assert {entity["display_alias"] for entity in body["entities"]} == {"g1", "s1"}
    assert len(body["connections"]) == 1
    assert body["connections"][0]["source_alias"] == "g1"
    assert body["connections"][0]["target_alias"] == "s1"


# ── GET /api/entity-display-search ───────────────────────────────────────────


class TestEntityDisplaySearch:
    def test_empty_query_returns_items(self, sync_client) -> None:
        r = sync_client.get("/api/entity-display-search?q=")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert "next_cursor" in body

    def test_query_returns_matches(self, sync_client) -> None:
        r = sync_client.get("/api/entity-display-search?q=Entity")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)

    def test_with_diagram_type_filter(self, sync_client) -> None:
        r = sync_client.get("/api/entity-display-search?q=&diagram_type=archimate-application")
        assert r.status_code == 200


# ── GET /api/diagram-types/{diagram_type}/entity-types ───────────────────────


class TestDiagramEntityTypes:
    def test_returns_items(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-types/archimate-application/entity-types")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_unknown_type_returns_404(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-types/no-such-type/entity-types")
        assert r.status_code == 404


# ── GET /api/diagram-types/{diagram_type}/connection-types ───────────────────


class TestDiagramConnectionTypes:
    def test_returns_items(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-types/archimate-application/connection-types")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)


# ── viewpoint-narrowed palette/picker (WU-E5a) ───────────────────────────────
# Unit coverage for the narrowing logic itself lives in
# tests/tools/test_viewpoint_scope_narrowing.py; these are endpoint-wiring smoke tests.


@pytest.fixture()
def sync_client_with_viewpoint(populated_root: Path):
    import dataclasses

    from starlette.testclient import TestClient

    from src.domain.concept_scope import ConceptScope
    from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = build_api_app(diagrams_router)
    definition = ViewpointDefinition(
        slug="narrow-app",
        version=1,
        name="Narrow Application",
        scope=ConceptScope(entity_types=frozenset({"application-component"}), connection_types=frozenset()),
    )
    catalogs = dataclasses.replace(
        build_runtime_catalogs(get_module_registry()), viewpoints=ViewpointCatalog(entries=(definition,))
    )
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    return TestClient(app)


class TestViewpointNarrowedPalette:
    def test_entity_types_narrowed_by_viewpoint(self, sync_client_with_viewpoint) -> None:
        r = sync_client_with_viewpoint.get(
            "/api/diagram-types/archimate-application/entity-types?viewpoint=narrow-app"
        )
        assert r.status_code == 200
        assert {item["artifact_type"] for item in r.json()["items"]} == {"application-component"}

    def test_connection_types_narrowed_to_empty(self, sync_client_with_viewpoint) -> None:
        r = sync_client_with_viewpoint.get(
            "/api/diagram-types/archimate-application/connection-types?viewpoint=narrow-app"
        )
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_unknown_viewpoint_is_404(self, sync_client_with_viewpoint) -> None:
        r = sync_client_with_viewpoint.get(
            "/api/diagram-types/archimate-application/entity-types?viewpoint=does-not-exist"
        )
        assert r.status_code == 404

    def test_entity_display_search_accepts_viewpoint_param(self, sync_client_with_viewpoint) -> None:
        r = sync_client_with_viewpoint.get(
            "/api/entity-display-search?q=&diagram_type=archimate-application&viewpoint=narrow-app"
        )
        assert r.status_code == 200

    def test_diagram_entity_discovery_accepts_viewpoint_param(self, sync_client_with_viewpoint) -> None:
        r = sync_client_with_viewpoint.get(
            "/api/diagram-entity-discovery?diagram_type=archimate-application&viewpoint=narrow-app"
        )
        assert r.status_code == 200


# ── GET /api/diagrams/{artifact_id}/context ──────────────────────────────────


class TestDiagramContext:
    def test_not_found_returns_404(self, sync_client) -> None:
        r = sync_client.get("/api/diagrams/DIAG@9.ZZZ.no-such/context")
        assert r.status_code == 404

    def test_found(self, sync_client) -> None:
        r = sync_client.get(f"/api/diagrams/{DIAG_ID}/context")
        assert r.status_code == 200


# ── GET /api/diagram-entity-discovery ────────────────────────────────────────


class TestDiagramEntityDiscovery:
    def test_returns_structure(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-entity-discovery")
        assert r.status_code == 200
        data = r.json()
        assert "search_results" in data
        assert "candidate_connections" in data
        assert "suggested_entities" in data

    def test_with_query(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-entity-discovery?q=Entity")
        assert r.status_code == 200

    def test_with_included_entity(self, sync_client) -> None:
        r = sync_client.get(
            f"/api/diagram-entity-discovery?included_entity_ids={ENT_ID}"
        )
        assert r.status_code == 200


# ── GET /api/diagram-refs ─────────────────────────────────────────────────────


class TestDiagramRefs:
    def test_no_shared_alias_returns_empty(self, sync_client) -> None:
        r = sync_client.get(f"/api/diagram-refs?source_id={ENT_ID}&target_id={ENT_ID}")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_unknown_entities_returns_empty(self, sync_client) -> None:
        r = sync_client.get("/api/diagram-refs?source_id=REQ@9.ZZZ.x&target_id=REQ@9.ZZZ.y")
        assert r.status_code == 200
        assert r.json()["items"] == []
