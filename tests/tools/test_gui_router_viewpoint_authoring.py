"""REST tests for the viewpoints management view's backend: full-catalog listing
(tier-tagged), the criteria-catalog registries snapshot, the plain-language summarize
endpoint, and create/edit/delete — the same ``persist_edit`` write path as the MCP
``artifact_viewpoint`` tool, mirrored here for the GUI's own save flow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.contracts.error_responses import install_error_contracts
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.viewpoint_authoring import router as viewpoint_authoring_router

httpx = pytest.importorskip("httpx")

_MINIMAL_DEFINITION = {"slug": "test-viewpoint", "version": 1, "name": "Test Viewpoint"}


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def client(engagement_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([engagement_root]))
    gui_state.init_state(repo, engagement_root, None)
    app = FastAPI(redirect_slashes=False)
    # Configured as the real application is, so a refusal is asserted in the envelope a client
    # actually receives rather than in FastAPI's default shape.
    install_error_contracts(app)
    app.include_router(viewpoint_authoring_router)
    return TestClient(app, raise_server_exceptions=False)


class TestCriteriaCatalog:
    def test_shape(self, client) -> None:
        resp = client.get("/api/viewpoints/criteria-catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "entity_types", "connection_types", "specialization_slugs",
            "entity_attribute_types", "connection_attribute_types",
            "entity_attribute_enums", "connection_attribute_enums", "symmetric_connection_types",
            "reserved_entity_paths", "reserved_connection_paths", "depth_cap", "bindings", "parameters", "derived",
            "connection_derivation", "entity_type_domains",
        }
        assert "application-component" in body["entity_types"]
        assert "type" in body["reserved_entity_paths"]
        assert body["bindings"]["select"] == ["entity", "connection"]
        assert "entity-id" in body["parameters"]["types"]
        assert body["derived"]["certainty"] == ["certain", "potential"]
        assert body["connection_derivation"]["archimate-realization"]["role"] == "structural"
        assert body["entity_type_domains"]["application-component"] == "application"
        # Reserved enumerable facets are always populated for the value picker.
        assert body["entity_attribute_enums"]["status"] == ["active", "deprecated", "draft"]
        assert "application" in body["entity_attribute_enums"]["domain"]
        # The group facet is fed from the project registry + observed record groups —
        # present (possibly empty) so the builder renders a picker, never free text.
        assert "group" in body["entity_attribute_enums"]

    def test_internal_entity_types_are_excluded_from_authoring_pickers(self, client) -> None:
        body = client.get("/api/viewpoints/criteria-catalog").json()
        assert "global-artifact-reference" not in body["entity_types"]


class TestReferencers:
    def test_empty_when_unreferenced(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        resp = client.get("/api/viewpoints/test-viewpoint/referencers")
        assert resp.status_code == 200
        assert resp.json() == {"referencers": []}

    def test_lists_referencing_diagram(self, client, engagement_root: Path) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        diagram_path = engagement_root / "diagram-catalog" / "diagrams" / "ARC@1000000042.DiagSch.ref.puml"
        diagram_path.write_text(
            """\
---
artifact-id: ARC@1000000042.DiagSch.ref
artifact-type: diagram
diagram-type: archimate-motivation
name: "Referencing Diagram"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
viewpoint:
  slug: test-viewpoint
  version: 1
---
@startuml
title Referencing Diagram
@enduml
""",
            encoding="utf-8",
        )
        gui_state.maybe_get_repo().refresh()
        resp = client.get("/api/viewpoints/test-viewpoint/referencers")
        assert resp.json() == {"referencers": [{"artifact_id": "ARC@1000000042.DiagSch.ref", "target_kind": "diagram"}]}


class TestSummarize:
    def test_renders_summary(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/summarize",
            json={
                "query": {
                    "query_schema": 1,
                    "entity_criteria": {"kind": "group", "conjunction": "and", "children": []},
                }
            },
        )
        assert resp.status_code == 200
        assert "Entity selection" in resp.json()["summary"]

    def test_malformed_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/summarize", json={"query": {"entity_criteria": {"kind": "nope"}}})
        assert resp.status_code == 400


class TestCreate:
    def test_dry_run_does_not_persist(self, client, engagement_root: Path) -> None:
        from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file

        resp = client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert load_viewpoint_catalog_file(engagement_root).get("test-viewpoint") is None

    def test_applies_when_dry_run_false(self, client, engagement_root: Path) -> None:
        from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file

        resp = client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        assert resp.json()["ok"] is True
        assert load_viewpoint_catalog_file(engagement_root).get("test-viewpoint") is not None

    def test_slug_collision_rejected(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        resp = client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        body = resp.json()
        assert body["ok"] is False
        assert body["issues"][0]["code"] == "slug-collision"

    def test_create_then_list_round_trip(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        listed = client.get("/api/viewpoints").json()
        entry = next(e for e in listed["viewpoints"] if e["slug"] == "test-viewpoint")
        assert entry["tier"] == "engagement"
        assert entry["name"] == "Test Viewpoint"


class TestEdit:
    def _seed(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})

    def test_descriptive_edit_without_bump_succeeds(self, client, engagement_root: Path) -> None:
        from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file

        self._seed(client)
        edited = {**_MINIMAL_DEFINITION, "description": "now described"}
        resp = client.put("/api/viewpoints/test-viewpoint", json={"definition": edited, "dry_run": False})
        assert resp.json()["ok"] is True
        assert load_viewpoint_catalog_file(engagement_root).get("test-viewpoint").description == "now described"

    def test_semantic_edit_without_bump_rejected(self, client) -> None:
        self._seed(client)
        edited = {**_MINIMAL_DEFINITION, "scope": {"entity_types": ["application-component"]}}
        resp = client.put("/api/viewpoints/test-viewpoint", json={"definition": edited, "dry_run": False})
        body = resp.json()
        assert body["ok"] is False
        assert any(i["code"] == "version-not-bumped" for i in body["issues"])

    def test_unknown_slug_rejected(self, client) -> None:
        resp = client.put(
            "/api/viewpoints/never-created",
            json={"definition": {"slug": "never-created", "version": 1, "name": "X"}, "dry_run": False},
        )
        assert resp.json()["issues"][0]["code"] == "unknown-slug"

    def test_a_definition_naming_another_viewpoint_is_refused(self, client) -> None:
        """The URL and the payload would disagree about which definition is being replaced, and
        there is no defensible winner — so neither wins."""
        self._seed(client)
        other = {**_MINIMAL_DEFINITION, "slug": "some-other-viewpoint"}
        resp = client.put("/api/viewpoints/test-viewpoint", json={"definition": other, "dry_run": True})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "validation_error"
        assert detail["details"]["field_errors"][0]["field"] == "body.definition.slug"


class TestReferenceReport:
    """The reference-integrity report on the catalogue list (Stream R, one of its three
    renderings). Ontology references are save-blocked, so a broken definition can only
    arise from a definition saved while valid and then invalidated by model change — modeled
    here by writing the catalog directly, then reading it back through the list endpoint."""

    def _write_broken(self, engagement_root: Path) -> None:
        from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
        from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointCatalog, ViewpointDefinition
        from src.infrastructure.viewpoint_declarations import write_viewpoint_catalog_file

        definition = ViewpointDefinition(
            slug="broken",
            version=1,
            name="Broken",
            selection_mode="query",
            query=ExecutableViewpointQuery(
                entity_criteria=EntityCriteriaGroup(
                    children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="ghost")),)
                )
            ),
        )
        write_viewpoint_catalog_file(engagement_root, ViewpointCatalog((definition,)))

    def test_list_reports_broken_reference_per_entry(self, client, engagement_root: Path) -> None:
        self._write_broken(engagement_root)
        entry = next(e for e in client.get("/api/viewpoints").json()["viewpoints"] if e["slug"] == "broken")
        broken = entry["broken_references"]
        assert any(b["reference"] == "ghost" and b["kind"] == "entity-type" for b in broken)
        assert all(b["severity"] == "ontology" for b in broken)

    def test_entity_id_default_is_savable_and_reported(self, client) -> None:
        # An entity-id anchor is warning-severity, NOT save-blocked — so it can be created
        # directly, and a nonexistent default surfaces as a broken entity-id reference.
        # (This is exactly what the e2e route walk relies on to seed a broken reference.)
        resp = client.post(
            "/api/viewpoints",
            json={
                "definition": {
                    "slug": "anchored",
                    "version": 1,
                    "name": "Anchored",
                    "selection_mode": "query",
                    "query": {
                        "query_schema": 1,
                        "parameters": [
                            {"name": "anchor", "type": "entity-id", "required": False, "default": "ENT@0.gone"}
                        ],
                    },
                },
                "dry_run": False,
            },
        )
        assert resp.json()["ok"] is True
        entry = next(e for e in client.get("/api/viewpoints").json()["viewpoints"] if e["slug"] == "anchored")
        assert any(
            b["reference"] == "ENT@0.gone" and b["kind"] == "entity-id" and b["severity"] == "entity-id"
            for b in entry["broken_references"]
        )

    def test_clean_definition_has_empty_report(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        entry = next(e for e in client.get("/api/viewpoints").json()["viewpoints"] if e["slug"] == "test-viewpoint")
        assert entry["broken_references"] == []

    def test_report_is_never_persisted(self, client, engagement_root: Path) -> None:
        self._write_broken(engagement_root)
        client.get("/api/viewpoints")  # computes the report
        catalog_files = list(engagement_root.rglob("*.y*ml")) + list(engagement_root.rglob("*.json"))
        assert catalog_files, "expected a written viewpoint catalog file"
        assert not any("broken_references" in path.read_text() for path in catalog_files)


class TestDelete:
    def test_deletes_existing(self, client, engagement_root: Path) -> None:
        from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file

        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        resp = client.delete("/api/viewpoints/test-viewpoint")
        # 204: a committed deletion has nothing to report, so it reports nothing.
        assert resp.status_code == 204
        assert resp.content == b""
        assert load_viewpoint_catalog_file(engagement_root).get("test-viewpoint") is None

    def test_dry_run_does_not_delete(self, client, engagement_root: Path) -> None:
        from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file

        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        resp = client.delete("/api/viewpoints/test-viewpoint?dry_run=true")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["dry_run"] is True
        assert load_viewpoint_catalog_file(engagement_root).get("test-viewpoint") is not None

    def test_blocked_while_referenced(self, client, engagement_root: Path) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        diagram_path = engagement_root / "diagram-catalog" / "diagrams" / "ARC@1000000042.DiagSch.ref.puml"
        diagram_path.write_text(
            """\
---
artifact-id: ARC@1000000042.DiagSch.ref
artifact-type: diagram
diagram-type: archimate-motivation
name: "Referencing Diagram"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
viewpoint:
  slug: test-viewpoint
  version: 1
---
@startuml
title Referencing Diagram
@enduml
""",
            encoding="utf-8",
        )
        gui_state.maybe_get_repo().refresh()
        resp = client.delete("/api/viewpoints/test-viewpoint")
        # A refusal is an error, not a 200 whose `ok` a caller has to remember to read.
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "viewpoint_referenced"
        assert detail["details"]["referencers"][0]["artifact_id"] == "ARC@1000000042.DiagSch.ref"
        assert detail["details"]["referencers"][0]["target_kind"] == "diagram"

    def test_unknown_slug_is_not_found(self, client) -> None:
        resp = client.delete("/api/viewpoints/never-created")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"

    def test_a_blocked_deletion_still_reports_its_plan_as_a_dry_run(self, client) -> None:
        """A dry run answers what *would* happen — including the reasons it would not — because a
        plan a caller cannot see is a plan they cannot act on."""
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        resp = client.delete("/api/viewpoints/never-created?dry_run=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["issues"][0]["code"] == "unknown-slug"


class TestLiteralSiblingSegments:
    """``/api/viewpoints/{slug}`` has literal siblings, and they must win.

    ``pins`` and ``criteria-catalog`` are collection-level singletons, not slugs. If the
    parameterised route matched first, a pin update would arrive at the replace handler and be
    rejected as a malformed definition — a 422 that says nothing about the real cause. The outcome
    is asserted here, not the matching rule, so a future reordering fails on what it breaks.
    """

    def test_a_literal_sibling_segment_is_not_read_as_a_slug(self, client) -> None:
        assert client.put("/api/viewpoints/pins", json={"slugs": []}).status_code == 200
        assert client.get("/api/viewpoints/criteria-catalog").status_code == 200

    def test_a_delete_of_a_literal_sibling_is_refused_not_reported_missing(self, client) -> None:
        """``DELETE /api/viewpoints/pins`` does reach the delete handler — the parameterised route
        matches where the pins route has no DELETE. It must not answer "no viewpoint named pins",
        which reads as an invitation to create one."""
        resp = client.delete("/api/viewpoints/pins")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "bad_request"

    def test_a_viewpoint_cannot_be_created_at_a_reserved_slug(self, client) -> None:
        """The refusal that matters: a definition named ``pins`` could be written and then never
        read back, because every request for it would resolve to the pin list."""
        resp = client.post(
            "/api/viewpoints",
            json={"definition": {"slug": "pins", "version": 1, "name": "Pins"}, "dry_run": True},
        )
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"]["message"]


class TestPins:
    def test_absence_is_empty(self, client) -> None:
        resp = client.get("/api/viewpoints/pins")
        assert resp.status_code == 200
        assert resp.json() == {"slugs": [], "pruned": []}

    def test_crud_round_trip(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        put_resp = client.put("/api/viewpoints/pins", json={"slugs": ["test-viewpoint"]})
        assert put_resp.status_code == 200
        assert put_resp.json() == {"slugs": ["test-viewpoint"]}

        get_resp = client.get("/api/viewpoints/pins")
        assert get_resp.json() == {"slugs": ["test-viewpoint"], "pruned": []}

        unpin_resp = client.put("/api/viewpoints/pins", json={"slugs": []})
        assert unpin_resp.json() == {"slugs": []}
        assert client.get("/api/viewpoints/pins").json() == {"slugs": [], "pruned": []}

    def test_module_shipped_definition_is_pinnable(self, client) -> None:
        resp = client.get("/api/viewpoints")
        module_slug = next(v["slug"] for v in resp.json()["viewpoints"] if v["tier"] == "module")
        put_resp = client.put("/api/viewpoints/pins", json={"slugs": [module_slug]})
        assert put_resp.status_code == 200
        assert client.get("/api/viewpoints/pins").json()["slugs"] == [module_slug]

    def test_unknown_slug_is_rejected(self, client) -> None:
        resp = client.put("/api/viewpoints/pins", json={"slugs": ["not-a-real-viewpoint"]})
        assert resp.status_code == 400

    def test_slug_removed_from_catalog_after_pinning_is_pruned_with_a_warning(self, client) -> None:
        client.post("/api/viewpoints", json={"definition": _MINIMAL_DEFINITION, "dry_run": False})
        client.put("/api/viewpoints/pins", json={"slugs": ["test-viewpoint"]})
        client.delete("/api/viewpoints/test-viewpoint")
        resp = client.get("/api/viewpoints/pins")
        assert resp.json() == {"slugs": [], "pruned": ["test-viewpoint"]}
