"""Functional tests for MCP write tool ``artifact_viewpoint`` (WU-E6a): create/edit/delete,
dry_run, version-bump/slug-collision/read-only/delete-blocked lifecycle rules, and the
create → list round-trip via the WU-E7a read tool (one shared catalog file, two tools).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.context import runtime_catalogs
from src.infrastructure.viewpoint_declarations import load_viewpoint_catalog_file


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    runtime_catalogs.cache_clear()
    yield
    runtime_catalogs.cache_clear()


_MINIMAL_DEFINITION = {"slug": "test-viewpoint", "version": 1, "name": "Test Viewpoint"}


class TestCreate:
    def test_dry_run_does_not_persist(self, repo: Path) -> None:
        result = mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, repo_root=str(repo))
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint") is None

    def test_applies_when_dry_run_false(self, repo: Path) -> None:
        result = mcp.artifact_viewpoint(
            action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo)
        )
        assert result["ok"] is True
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint") is not None

    def test_slug_collision_rejected(self, repo: Path) -> None:
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))
        result = mcp.artifact_viewpoint(
            action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo)
        )
        assert result["ok"] is False
        assert result["issues"][0]["code"] == "slug-collision"

    def test_create_then_list_round_trip(self, repo: Path) -> None:
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))
        fn = mcp.mcp_read._tool_manager._tools["artifact_query_viewpoint"].fn
        listed = fn(action="list", repo_root=str(repo))
        slugs = [entry["slug"] for entry in listed["viewpoints"]]
        assert "test-viewpoint" in slugs

    def test_binding_cycle_is_reported_with_definition_path(self, repo: Path) -> None:
        definition = {
            **_MINIMAL_DEFINITION,
            "query": {
                "query_schema": 1,
                "bindings": [
                    {
                        "name": "first",
                        "result_type": "entities[]",
                        "select": "entities",
                        "criteria": {
                            "kind": "group",
                            "conjunction": "and",
                            "children": [
                                {
                                    "kind": "condition",
                                    "attribute": "type",
                                    "comparator": "eq",
                                    "value": {"from": "binding", "name": "second"},
                                }
                            ],
                        },
                    },
                    {
                        "name": "second",
                        "result_type": "entities[]",
                        "select": "entities",
                        "criteria": {
                            "kind": "group",
                            "conjunction": "and",
                            "children": [
                                {
                                    "kind": "condition",
                                    "attribute": "type",
                                    "comparator": "eq",
                                    "value": {"from": "binding", "name": "first"},
                                }
                            ],
                        },
                    },
                ],
            },
        }
        result = mcp.artifact_viewpoint(action="create", definition=definition, repo_root=str(repo))
        cycle = next(issue for issue in result["issues"] if issue["code"] == "binding-cycle")
        assert cycle["path"] == "/query/bindings"


class TestEdit:
    def _seed(self, repo: Path) -> None:
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))

    def test_descriptive_edit_without_bump_succeeds(self, repo: Path) -> None:
        self._seed(repo)
        edited = {**_MINIMAL_DEFINITION, "description": "now described"}
        result = mcp.artifact_viewpoint(action="edit", definition=edited, dry_run=False, repo_root=str(repo))
        assert result["ok"] is True
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint").description == "now described"

    def test_semantic_edit_without_bump_rejected(self, repo: Path) -> None:
        self._seed(repo)
        edited = {**_MINIMAL_DEFINITION, "scope": {"entity_types": ["application-component"]}}
        result = mcp.artifact_viewpoint(action="edit", definition=edited, dry_run=False, repo_root=str(repo))
        assert result["ok"] is False
        assert any(i["code"] == "version-not-bumped" for i in result["issues"])

    def test_semantic_edit_with_bump_succeeds(self, repo: Path) -> None:
        self._seed(repo)
        edited = {**_MINIMAL_DEFINITION, "version": 2, "scope": {"entity_types": ["application-component"]}}
        result = mcp.artifact_viewpoint(action="edit", definition=edited, dry_run=False, repo_root=str(repo))
        assert result["ok"] is True

    def test_parameter_declaration_change_requires_bump(self, repo: Path) -> None:
        definition = {
            **_MINIMAL_DEFINITION,
            "query": {"query_schema": 1, "parameters": [{"name": "limit", "type": "integer"}]},
        }
        assert mcp.artifact_viewpoint(action="create", definition=definition, dry_run=False, repo_root=str(repo))["ok"]
        edited = {
            **definition,
            "query": {
                "query_schema": 1,
                "parameters": [
                    {"name": "limit", "type": "integer"},
                    {"name": "include_archived", "type": "boolean", "required": False},
                ],
            },
        }
        result = mcp.artifact_viewpoint(action="edit", definition=edited, dry_run=False, repo_root=str(repo))
        assert any(issue["code"] == "version-not-bumped" for issue in result["issues"])

    def test_unknown_slug_rejected(self, repo: Path) -> None:
        result = mcp.artifact_viewpoint(
            action="edit", definition={"slug": "never-created", "version": 1, "name": "X"},
            dry_run=False, repo_root=str(repo),
        )
        assert result["ok"] is False
        assert result["issues"][0]["code"] == "unknown-slug"


_REFERENCING_DIAGRAM = """\
---
artifact-id: ARC@1000000042.DiagSch.referencing-diagram
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
"""


class TestDelete:
    def test_deletes_existing(self, repo: Path) -> None:
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))
        result = mcp.artifact_viewpoint(action="delete", slug="test-viewpoint", dry_run=False, repo_root=str(repo))
        assert result["ok"] is True
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint") is None

    def test_dry_run_does_not_delete(self, repo: Path) -> None:
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))
        result = mcp.artifact_viewpoint(action="delete", slug="test-viewpoint", repo_root=str(repo))
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint") is not None

    def test_blocked_while_referenced_by_real_diagram(self, repo: Path) -> None:
        # A raw fixture file (not the MCP diagram-write tool): this test's concern is
        # referencer *discovery* over a real ArtifactRepository, independent of the
        # diagram-write verifier's own (unrelated, out-of-scope) catalog resolution.
        mcp.artifact_viewpoint(action="create", definition=_MINIMAL_DEFINITION, dry_run=False, repo_root=str(repo))
        diagram_path = repo / "diagram-catalog" / "diagrams" / "ARC@1000000042.DiagSch.referencing-diagram.puml"
        diagram_path.write_text(_REFERENCING_DIAGRAM, encoding="utf-8")

        result = mcp.artifact_viewpoint(action="delete", slug="test-viewpoint", dry_run=False, repo_root=str(repo))
        assert result["ok"] is False
        assert result["issues"][0]["code"] == "delete-blocked-referenced"
        assert result["referencers"][0]["artifact_id"] == "ARC@1000000042.DiagSch.referencing-diagram"
        assert load_viewpoint_catalog_file(repo).get("test-viewpoint") is not None


class TestToolDescription:
    def test_registered_on_write_not_read(self) -> None:
        write_names = {t.name for t in mcp.mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]
        read_names = {t.name for t in mcp.mcp_read._tool_manager.list_tools()}  # type: ignore[attr-defined]
        assert "artifact_viewpoint" in write_names
        assert "artifact_viewpoint" not in read_names

    def test_expected_parameters_present(self) -> None:
        tool = mcp.mcp_write._tool_manager._tools["artifact_viewpoint"]
        params = set(tool.parameters.get("properties", {}).keys())
        assert {"action", "slug", "definition", "dry_run", "repo_root"} <= params

    def test_description_mentions_help_topic_and_lifecycle_rules(self) -> None:
        desc = mcp.mcp_write._tool_manager._tools["artifact_viewpoint"].description
        assert "artifact_help" in desc
        assert "version bump" in desc
        assert "delete" in desc
