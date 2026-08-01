"""Functional tests for MCP read tool ``artifact_query_viewpoint``: ``list``/
``execute`` actions, limit default/explicit/clamp, and MCP/REST parity (one shared fixture,
both transports).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import src.infrastructure.mcp.artifact_mcp.query_viewpoint_tools as qvt
from src.application.viewpoints.pins import save_pinned_slugs
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointCatalog, ViewpointDefinition
from src.infrastructure.mcp import mcp_artifact_server as mcp
from tests.support.api_app import build_api_app


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make(repo: Path, artifact_type: str, name: str) -> str:
    r = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert r["wrote"], r
    return str(r["artifact_id"])


def _fn():
    return mcp.mcp_read._tool_manager._tools["artifact_query_viewpoint"].fn


def _catalog_with(*definitions: ViewpointDefinition) -> ViewpointCatalog:
    return ViewpointCatalog(entries=definitions)


@pytest.fixture()
def catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

    return build_runtime_catalogs(get_module_registry())


def _install_catalog(monkeypatch: pytest.MonkeyPatch, catalogs, catalog: ViewpointCatalog) -> None:
    # merged_catalog comes from load_effective_viewpoint_catalog(roots), scoped to the
    # request's own repo_root rather than the workspace-singleton catalogs — patch that
    # instead of runtime_catalogs, which still supplies ontology/registries only.
    monkeypatch.setattr(qvt, "load_effective_viewpoint_catalog", lambda roots: catalog)
    monkeypatch.setattr(qvt, "process_runtime_catalogs", lambda: catalogs)


class TestListAction:
    def test_returns_entries_sorted_by_slug_with_summaries(self, monkeypatch, catalogs) -> None:
        definition_b = ViewpointDefinition(
            slug="b-viewpoint", version=1, name="B", query=ExecutableViewpointQuery()
        )
        definition_a = ViewpointDefinition(slug="a-viewpoint", version=2, name="A")
        _install_catalog(monkeypatch, catalogs, _catalog_with(definition_b, definition_a))

        result = _fn()(action="list")
        slugs = [entry["slug"] for entry in result["viewpoints"]]
        assert slugs == ["a-viewpoint", "b-viewpoint"]

        b_entry = next(e for e in result["viewpoints"] if e["slug"] == "b-viewpoint")
        assert b_entry["version"] == 1
        assert b_entry["scope_summary"] == {"unrestricted": True}
        assert b_entry["query_summary"] is not None

        # A query-less definition's listing describes its ACTIVE selection — the
        # scope-derived query — never a blank.
        a_entry = next(e for e in result["viewpoints"] if e["slug"] == "a-viewpoint")
        assert a_entry["query_summary"] is not None
        assert "any entity" in a_entry["query_summary"]

    def test_pinned_flag_reflects_the_engagement_repo_local_pins_file(self, monkeypatch, catalogs, repo: Path) -> None:
        definition_a = ViewpointDefinition(slug="a-viewpoint", version=1, name="A")
        definition_b = ViewpointDefinition(slug="b-viewpoint", version=1, name="B")
        _install_catalog(monkeypatch, catalogs, _catalog_with(definition_a, definition_b))
        save_pinned_slugs(repo, ("a-viewpoint",))

        result = _fn()(action="list", repo_root=str(repo), repo_scope="engagement")
        pinned = {entry["slug"]: entry["pinned"] for entry in result["viewpoints"]}
        assert pinned == {"a-viewpoint": True, "b-viewpoint": False}


class TestExecuteAction:
    def test_execute_by_slug(self, monkeypatch, catalogs, repo: Path) -> None:
        entity_id = _make(repo, "application-component", "Exec Entity")
        definition = ViewpointDefinition(slug="exec-test", version=1, name="Exec", query=ExecutableViewpointQuery())
        _install_catalog(monkeypatch, catalogs, _catalog_with(definition))

        result = _fn()(action="execute", slug="exec-test", repo_root=str(repo), repo_scope="engagement")
        assert result["slug"] == "exec-test"
        assert entity_id in result["entity_ids"]
        assert result["query_summary"]

    def test_execute_ad_hoc_query(self, monkeypatch, catalogs, repo: Path) -> None:
        entity_id = _make(repo, "application-component", "Ad Hoc Entity")
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())

        result = _fn()(action="execute", query={}, repo_root=str(repo), repo_scope="engagement")
        assert result["slug"] is None
        assert entity_id in result["entity_ids"]

    def test_unknown_slug_raises(self, monkeypatch, catalogs, repo: Path) -> None:
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        with pytest.raises(ValueError):
            _fn()(action="execute", slug="does-not-exist", repo_root=str(repo), repo_scope="engagement")

    def test_both_slug_and_query_raises(self, monkeypatch, catalogs, repo: Path) -> None:
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        with pytest.raises(ValueError):
            _fn()(action="execute", slug="x", query={}, repo_root=str(repo), repo_scope="engagement")


class TestLimit:
    def test_default_limit_is_mcp_default(self, monkeypatch, catalogs, repo: Path) -> None:
        for i in range(3):
            _make(repo, "application-component", f"Entity {i}")
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        monkeypatch.setattr(
            "src.config.settings.load_settings",
            lambda: {"viewpoints": {"execution_max_entities": 500, "execution_default_entity_limit_mcp": 2}},
        )
        result = _fn()(action="execute", query={}, repo_root=str(repo), repo_scope="engagement")
        assert result["entity_limit"] == 2
        assert result["returned_entity_count"] == 2
        assert result["truncated"] is True

    def test_explicit_limit_overrides_default(self, monkeypatch, catalogs, repo: Path) -> None:
        for i in range(3):
            _make(repo, "application-component", f"Entity {i}")
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        result = _fn()(action="execute", query={}, limit=1, repo_root=str(repo), repo_scope="engagement")
        assert result["entity_limit"] == 1

    def test_limit_clamped_to_hard_cap(self, monkeypatch, catalogs, repo: Path) -> None:
        _make(repo, "application-component", "Solo Entity")
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        monkeypatch.setattr(
            "src.config.settings.load_settings",
            lambda: {"viewpoints": {"execution_max_entities": 1, "execution_default_entity_limit_mcp": 200}},
        )
        result = _fn()(action="execute", query={}, limit=1000, repo_root=str(repo), repo_scope="engagement")
        assert result["entity_limit"] == 1


class TestMcpRestParity:
    def test_parameterized_derived_query_has_same_content(self, monkeypatch, catalogs, repo: Path) -> None:
        from starlette.testclient import TestClient

        from src.application.artifacts.repository import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers.viewpoints.router import fresh_viewpoints_runtime_catalogs_dependency
        from src.infrastructure.rest.routers.viewpoints.router import router as viewpoints_router

        entity_id = _make(repo, "application-component", "Parameterized Entity")
        _install_catalog(monkeypatch, catalogs, ViewpointCatalog.empty())
        query = {
            "query_schema": 1,
            "parameters": [{"name": "entity_type", "type": "string"}],
            "entity_criteria": {
                "kind": "group",
                "conjunction": "and",
                "children": [
                    {
                        "kind": "condition",
                        "attribute": "type",
                        "comparator": "eq",
                        "value": {"from": "parameter", "name": "entity_type"},
                    }
                ],
            },
            "connections": {"enabled": True, "traversal": "derived", "max_hops": 2},
        }
        parameters = {"entity_type": "application-component"}
        mcp_result = _fn()(
            action="execute", query=query, parameters=parameters, limit=500,
            repo_root=str(repo), repo_scope="engagement",
        )

        gui_repo = ArtifactRepository(shared_artifact_index([repo]))
        gui_state.init_state(gui_repo, repo, None)
        app = build_api_app(viewpoints_router)
        app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: catalogs
        rest_result = TestClient(app).post(
            "/api/viewpoints/execute", json={"query": query, "parameters": parameters, "limit": 500}
        ).json()

        assert entity_id in mcp_result["entity_ids"]
        mcp_json = json.loads(json.dumps(mcp_result))
        for key in set(mcp_json) - {"executed_at", "duration_ms", "index_generation"}:
            assert mcp_json[key] == rest_result[key], key

    def test_same_query_same_content_both_transports(self, monkeypatch, catalogs, repo: Path) -> None:
        from starlette.testclient import TestClient

        from src.application.artifacts.repository import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers.viewpoints.router import fresh_viewpoints_runtime_catalogs_dependency
        from src.infrastructure.rest.routers.viewpoints.router import router as viewpoints_router

        entity_id = _make(repo, "application-component", "Parity Entity")
        definition = ViewpointDefinition(slug="parity-test", version=1, name="P", query=ExecutableViewpointQuery())
        merged = _catalog_with(definition)
        patched_catalogs = dataclasses.replace(catalogs, viewpoints=merged)
        monkeypatch.setattr(qvt, "load_effective_viewpoint_catalog", lambda roots: merged)
        monkeypatch.setattr(qvt, "process_runtime_catalogs", lambda: patched_catalogs)

        # Same explicit limit on both transports — MCP and REST intentionally differ in
        # their *default* limit (§7.1: MCP defaults lower to protect agent context), which
        # is not a parity concern; content parity is about the same query + same limit.
        mcp_result = _fn()(
            action="execute", slug="parity-test", limit=500, repo_root=str(repo), repo_scope="engagement"
        )

        gui_repo = ArtifactRepository(shared_artifact_index([repo]))
        gui_state.init_state(gui_repo, repo, None)
        app = build_api_app(viewpoints_router)
        app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: patched_catalogs
        client = TestClient(app)
        rest_result = client.post("/api/viewpoints/execute", json={"slug": "parity-test", "limit": 500}).json()

        assert entity_id in mcp_result["entity_ids"]
        # Round-trip the MCP result through JSON so tuple-vs-list is not a false mismatch —
        # both transports serialize to JSON in practice; only the in-process dataclass differs.
        mcp_result_json = json.loads(json.dumps(mcp_result))
        volatile = {"executed_at", "duration_ms", "index_generation"}
        for key in set(mcp_result_json) - volatile:
            assert mcp_result_json[key] == rest_result[key], key


class TestHelpTopic:
    def test_write_help_carries_viewpoints_topic(self) -> None:
        result = mcp.artifact_help()
        assert "viewpoints" in result
        topic = result["viewpoints"]
        assert "comparators" in topic
        assert "reserved_entity_paths" in topic
        assert "canonical_form_example" in topic
        assert topic["parameters"]["types"]
        assert topic["bindings"]["quantifiers"] == ["any", "all"]
        assert topic["derived_attributes"]["traversal"] == ["direct", "derived"]
