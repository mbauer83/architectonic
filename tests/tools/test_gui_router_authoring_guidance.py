"""Tests for GET /api/authoring-guidance (the REST wrapper around get_type_guidance).

Covers: entity_type/domain CSV filters, diagram_type guidance, pair-legality via target,
error passthrough for unknown types, and REST/domain-function parity.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry, install_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.authoring_guidance import router as authoring_guidance_router
from src.infrastructure.viewpoint_declarations import load_effective_viewpoint_catalog
from src.infrastructure.write.artifact_write.type_guidance import get_type_guidance
from tests.support.api_app import build_api_app

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
    # `build_api_app`, not a bare `FastAPI()`: without the error contracts a raised `ApiError` is a 500
    # and the test asserts a shape no client receives.
    app = build_api_app(authoring_guidance_router)
    install_module_registry(app)
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


def _without_nulls(value: object) -> object:
    """``value`` with every null-valued key dropped, at every depth.

    The route serves the use case's payload under one null policy — unset optionals are absent, not
    null — so comparing the two verbatim compares the payload against a *different* spelling of
    itself. Normalizing the use case side is what keeps this a test of the route's fidelity rather
    than of its serializer's defaults.
    """
    if isinstance(value, dict):
        return {k: _without_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_without_nulls(v) for v in value]
    return value


class TestEntityTypeAndDomainFilters:
    def test_entity_type_filter_matches_domain_function(
        self, client: TestClient, isolated_catalogs: RuntimeCatalogs, engagement_root: Path,
    ) -> None:
        resp = client.get("/api/authoring-guidance", params={"entity_type": "requirement"})
        assert resp.status_code == 200
        assert resp.json() == _without_nulls(get_type_guidance(
            filter=["requirement"], catalogs=isolated_catalogs, repo_root=engagement_root
        ))

    def test_domain_filter_matches_domain_function(
        self, client: TestClient, isolated_catalogs: RuntimeCatalogs, engagement_root: Path,
    ) -> None:
        resp = client.get("/api/authoring-guidance", params={"domain": "motivation"})
        assert resp.status_code == 200
        assert resp.json() == _without_nulls(get_type_guidance(
            filter=["motivation"], catalogs=isolated_catalogs, repo_root=engagement_root
        ))

    def test_connection_types_carry_the_effective_metadata_schema(
        self, client: TestClient, engagement_root: Path
    ) -> None:
        """Connections have no schema endpoint of their own, so the guidance payload
        carries the effective merged metadata schema each pair authors against."""
        from src.application.artifacts.schema import clear_schema_cache

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
        from src.application.artifacts.schema import clear_schema_cache

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

    def test_unknown_diagram_type_is_a_422(self, client: TestClient) -> None:
        """422, not a 200 carrying an `error` string: the whole request failed, and a success status is
        only defensible for a mixed result that says which parts succeeded."""
        resp = client.get("/api/authoring-guidance", params={"diagram_type": "not-a-type"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "validation_error"
        assert detail["details"]["field_errors"][0]["field"] == "diagram_type"


class TestPairLegality:
    def test_target_with_entity_type_returns_pair_guidance(self, client: TestClient) -> None:
        resp = client.get(
            "/api/authoring-guidance", params={"entity_type": "requirement", "target": "goal"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pair_guidance"]["source"] == "requirement"
        assert body["pair_guidance"]["target"] == "goal"

    def test_target_without_filter_is_a_422(self, client: TestClient) -> None:
        resp = client.get("/api/authoring-guidance", params={"target": "goal"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "validation_error"
        # The field the use case named, not one the adapter guessed by matching the message.
        assert detail["details"]["field_errors"][0]["field"] == "filter"


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


# ── a type the ontology knows but never offers guidance for ──────────────────


def test_an_internal_type_is_answered_with_nothing_rather_than_refused(client) -> None:  # noqa: ANN001
    """Opening a global artifact reference asked three panels for guidance about it, and each got a
    422 saying "provide known entity-type names" — about a name the ontology knows perfectly well.

    Internal types are excluded from the guidance catalogue on purpose: they are produced by
    promotion rather than authored, so there is nothing to offer. That is an answer, not a mistake by
    the caller, and the difference is what this restores.
    """
    response = client.get("/api/authoring-guidance?entity_type=global-artifact-reference")

    assert response.status_code == 200, response.text
    assert response.json()["entity_types"] == []


def test_a_name_the_ontology_has_never_heard_of_is_still_refused(client) -> None:  # noqa: ANN001
    """The refusal has to keep working, or a caller's typo becomes an empty answer they believe."""
    response = client.get("/api/authoring-guidance?entity_type=not-a-type-at-all")

    assert response.status_code == 422
    assert "not-a-type-at-all" in response.text


def test_an_internal_type_beside_a_real_one_still_answers_for_the_real_one(client) -> None:  # noqa: ANN001
    """A mixed filter is not an all-or-nothing question."""
    response = client.get("/api/authoring-guidance?entity_type=requirement,global-artifact-reference")

    assert response.status_code == 200, response.text
    assert [entry["name"] for entry in response.json()["entity_types"]] == ["requirement"]
