"""Tests for GET /api/authoring-guidance (the REST wrapper around get_type_guidance).

Covers: entity_type/domain CSV filters, diagram_type guidance, pair-legality via target,
error passthrough for unknown types, and REST/domain-function parity.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.application.artifact_repository import ArtifactRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry, install_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.authoring_guidance import router as authoring_guidance_router
from src.infrastructure.viewpoint_declarations import load_effective_viewpoint_catalog
from src.infrastructure.write.artifact_write.type_guidance import get_type_guidance

httpx = pytest.importorskip("httpx")


@pytest.fixture
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture
def client(engagement_root: Path) -> TestClient:
    repo = ArtifactRepository(shared_artifact_index([engagement_root]))
    gui_state.init_state(repo, engagement_root, None)
    app = FastAPI()
    install_module_registry(app)
    app.include_router(authoring_guidance_router)
    return TestClient(app)


@pytest.fixture
def isolated_catalogs(engagement_root: Path) -> RuntimeCatalogs:
    """The same fresh-viewpoints catalogs the REST endpoint builds for `engagement_root` —
    needed so the REST/domain-function parity tests below compare against this isolated
    repo rather than `get_type_guidance`'s own no-`catalogs`-given default, which resolves
    the ambient configured workspace (whatever real repo this machine happens to have set
    up) rather than the test's isolated one."""
    return dataclasses.replace(
        build_runtime_catalogs(get_module_registry()),
        viewpoints=load_effective_viewpoint_catalog([engagement_root]),
    )


class TestEntityTypeAndDomainFilters:
    def test_entity_type_filter_matches_domain_function(
        self, client: TestClient, isolated_catalogs: RuntimeCatalogs, engagement_root: Path,
    ) -> None:
        resp = client.get("/api/authoring-guidance", params={"entity_type": "requirement"})
        assert resp.status_code == 200
        assert resp.json() == get_type_guidance(
            filter=["requirement"], catalogs=isolated_catalogs, repo_root=engagement_root
        )

    def test_domain_filter_matches_domain_function(
        self, client: TestClient, isolated_catalogs: RuntimeCatalogs, engagement_root: Path,
    ) -> None:
        resp = client.get("/api/authoring-guidance", params={"domain": "motivation"})
        assert resp.status_code == 200
        assert resp.json() == get_type_guidance(
            filter=["motivation"], catalogs=isolated_catalogs, repo_root=engagement_root
        )

    def test_connection_types_carry_the_effective_metadata_schema(
        self, client: TestClient, engagement_root: Path
    ) -> None:
        """Connections have no schema endpoint of their own, so the guidance payload
        carries the effective merged metadata schema each pair authors against."""
        from src.application.artifact_schema import clear_schema_cache

        schemata = engagement_root / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True, exist_ok=True)
        (schemata / "connection-metadata.archimate-assignment.schema.json").write_text(
            '{"properties": {"cadence": {"type": "string"}}}', encoding="utf-8"
        )
        clear_schema_cache()
        body = client.get("/api/authoring-guidance", params={"entity_type": "requirement"}).json()
        assignment = next(e for e in body["connection_types"] if e["name"] == "archimate-assignment")
        assert assignment["metadata_schema"]["properties"] == ["cadence"]
        assert assignment["metadata_schema"]["quarantined"] is False
        # Every declared specialization carries its own merged schema, not just the type.
        assert all("metadata_schema" in s for s in assignment["specializations"])

    def test_base_schema_is_included_without_specializations(
        self, client: TestClient, engagement_root: Path
    ) -> None:
        from src.application.artifact_schema import clear_schema_cache

        schemata = engagement_root / ".arch-repo" / "schemata"
        schemata.mkdir(parents=True, exist_ok=True)
        (schemata / "connection-metadata.archimate-influence.schema.json").write_text(
            '{"properties": {"polarity": {"type": "string"}}}', encoding="utf-8"
        )
        clear_schema_cache()
        body = client.get("/api/authoring-guidance", params={"entity_type": "goal"}).json()
        influence = next(e for e in body["connection_types"] if e["name"] == "archimate-influence")
        assert influence["specializations"] == []
        assert influence["metadata_schema"]["properties"] == ["polarity"]

    def test_no_params_returns_all_entity_types(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance")
        assert resp.status_code == 200
        body = resp.json()
        assert "entity_types" in body
        assert body["total"] > 0

    def test_csv_entity_type_filter(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"entity_type": "requirement,goal"})
        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()["entity_types"]}
        assert names == {"requirement", "goal"}


class TestDiagramTypeGuidance:
    def test_diagram_type_returns_guidance_block(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"diagram_type": "activity"})
        assert resp.status_code == 200
        body = resp.json()
        assert "diagram_type_guidance" in body
        assert body["diagram_type_guidance"]["name"] == "activity"

    def test_unknown_diagram_type_returns_error(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"diagram_type": "not-a-type"})
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestPairLegality:
    def test_target_with_entity_type_returns_pair_guidance(self, client: TestClient) -> None:
        resp = client.get(
            "/api/authoring-guidance", params={"entity_type": "requirement", "target": "goal"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pair_guidance"]["source"] == "requirement"
        assert body["pair_guidance"]["target"] == "goal"

    def test_target_without_filter_returns_error(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"target": "goal"})
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestInternalTypesExcluded:
    """Internal entity types (promotion-created only, e.g. global-artifact-reference) must never
    be offered by any authoring-guidance surface — the create path rejects them outright."""

    def test_domain_guidance_never_lists_internal_types(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"domain": "common"})
        names = {e["name"] for e in resp.json()["entity_types"]}
        assert "global-artifact-reference" not in names
        assert "process" in names

    def test_unfiltered_guidance_never_lists_internal_types(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance")
        names = {e["name"] for e in resp.json()["entity_types"]}
        assert "global-artifact-reference" not in names

    def test_explicit_request_for_internal_type_is_not_honored(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"entity_type": "global-artifact-reference"})
        body = resp.json()
        listed = {e["name"] for e in body.get("entity_types", [])}
        assert "global-artifact-reference" not in listed
