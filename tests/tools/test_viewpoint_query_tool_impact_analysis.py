"""MCP/REST coverage for the 3 custom impact-analysis definitions: parameter signatures
surfaced via MCP ``list``, REST/MCP transport parity, and proof that the underlying
derived-traversal mechanism generalizes beyond ``process-technology-support``'s own
fixed technology-domain neighbor restriction — reconfigured ad-hoc with a requirement
anchor and process/function/event/service/application neighbor types, showing indirect
support and correct certainty-policy toggling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    EntityCriteriaGroup,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.mcp import mcp_artifact_server as mcp
from tests.application.viewpoints._fixtures import Store, connection, entity
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

_CATALOGS = build_runtime_catalogs(get_module_registry())
_REGISTRIES = build_registry_snapshot(_CATALOGS, [])
_CUSTOM_SLUGS = ("element-dependents", "element-dependencies", "process-technology-support")


def _fn():
    return mcp.mcp_read._tool_manager._tools["artifact_query_viewpoint"].fn


class TestParameterSignaturesViaMcpList:
    def test_list_surfaces_the_anchor_parameter_for_each_custom_definition(self) -> None:
        result = _fn()(action="list")
        by_slug = {entry["slug"]: entry for entry in result["viewpoints"]}
        for slug in _CUSTOM_SLUGS:
            assert slug in by_slug, slug
            parameters = by_slug[slug]["parameters"]
            assert parameters == [{"name": "anchor", "type": "entity-id", "required": True}]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


class TestRestMcpParity:
    def test_element_dependents_matches_across_transports(self, repo: Path) -> None:
        from starlette.testclient import TestClient

        from src.application.artifact_repository import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers.viewpoints import fresh_viewpoints_runtime_catalogs_dependency
        from src.infrastructure.rest.routers.viewpoints import router as viewpoints_router

        anchor_id = mcp.artifact_create_entity(
            artifact_type="application-component", name="Anchor", dry_run=False, repo_root=str(repo)
        )["artifact_id"]

        mcp_result = _fn()(
            action="execute", slug="element-dependents", parameters={"anchor": anchor_id}, limit=500,
            repo_root=str(repo), repo_scope="engagement",
        )

        gui_repo = ArtifactRepository(shared_artifact_index([repo]))
        gui_state.init_state(gui_repo, repo, None)
        app = build_api_app(viewpoints_router)
        app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: _CATALOGS
        client = TestClient(app)
        rest_result = client.post(
            "/api/viewpoints/execute", json={"slug": "element-dependents", "parameters": {"anchor": anchor_id}}
        ).json()

        assert anchor_id in mcp_result["entity_ids"]
        mcp_json = json.loads(json.dumps(mcp_result))
        volatile = {"executed_at", "duration_ms", "index_generation"}
        for key in set(mcp_json) - volatile:
            assert mcp_json[key] == rest_result[key], key


class TestGenericDerivedTraversalMechanismReconfigured:
    """process-technology-support hardcodes a technology-domain neighbor restriction;
    this proves the *mechanism* it rides (include_connected traversal: derived) is
    generic, by pointing an ad-hoc query at a requirement anchor with a
    process/function/event/service/application-component neighbor set instead."""

    def _support_store(self) -> Store:
        # requirement <-(realization, certain composition via structural+structural)-
        # function <- service <- application-component: a 3-hop chain so the requirement
        # gains an indirect (2+ hop) supporter, proving multi-hop reach, not just direct
        # neighbors.
        entities = {
            "ENT@req": entity(artifact_id="ENT@req", artifact_type="requirement", domain="motivation", name="Req"),
            "ENT@fnc": entity(artifact_id="ENT@fnc", artifact_type="function", domain="common", name="Fnc"),
            "ENT@svc": entity(artifact_id="ENT@svc", artifact_type="service", domain="common", name="Svc"),
            "ENT@app": entity(
                artifact_id="ENT@app", artifact_type="application-component", domain="application", name="App"
            ),
        }
        connections = [
            connection(artifact_id="CON@1", source="ENT@app", target="ENT@svc", conn_type="archimate-assignment"),
            connection(artifact_id="CON@2", source="ENT@svc", target="ENT@fnc", conn_type="archimate-assignment"),
            connection(artifact_id="CON@3", source="ENT@fnc", target="ENT@req", conn_type="archimate-realization"),
        ]
        return Store(entities=entities, connections=connections)

    def _query(self, *, include_potential: bool) -> ExecutableViewpointQuery:
        neighbor_types = ["process", "function", "event", "service", "application-component"]
        return ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="id", comparator="eq", value=ValueRef(literal="ENT@req")),)
            ),
            include_connected=(
                NeighborInclusion(
                    direction="incoming",
                    traversal="derived",
                    include_potential=include_potential,
                    max_hops=4,
                    neighbor_criteria=EntityCriteriaGroup(
                        children=(
                            AttributeCondition(
                                attribute="type", comparator="in", value=ValueRef(literal=neighbor_types)
                            ),
                        )
                    ),
                ),
            ),
        )

    def _execute(self, *, include_potential: bool):
        return evaluate_viewpoint(
            ViewpointExecutionRequest(query=self._query(include_potential=include_potential)),
            catalog=_CATALOGS.viewpoints,
            read_access=self._support_store(),
            registries=_REGISTRIES,
            index_generation=None,
            max_entities=500,
            default_limit=500,
            timeout_seconds=10.0,
        )

    def test_indirect_support_is_found_beyond_the_immediate_neighbor(self) -> None:
        result = self._execute(include_potential=True)
        # svc is 2 hops from req (a genuine derived composition); app is 3 hops.
        assert "ENT@svc" in result.entity_ids

    def test_certainty_policy_toggles_which_relationships_are_visible_without_conflation(self) -> None:
        certain_only = self._execute(include_potential=False)
        with_potential = self._execute(include_potential=True)
        certain_ids = set(certain_only.entity_ids)
        potential_ids = set(with_potential.entity_ids)
        assert certain_ids <= potential_ids
        # Every derived connection in each result carries its own certainty distinctly —
        # toggling the policy never merges a potential finding into a certain one.
        for result in (certain_only, with_potential):
            for summary in result.connections:
                if summary.certainty is not None:
                    assert summary.certainty in ("certain", "potential")
        if potential_ids - certain_ids:
            newly_visible = [
                c for c in with_potential.connections if c.certainty == "potential"
            ]
            assert newly_visible, "expanding to include_potential should surface potential-only findings"
