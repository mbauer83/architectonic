"""Snapshot tests for MCP tool descriptions and schemas.

Pins the description text and parameter schemas for the two tools whose
behavior changed in the diagram-refresh and edge-label work, so that
future drift is caught automatically rather than by manual inspection.

Checked properties:
- artifact_edit_diagram: projection-aware auto-sync description (refresh work);
  edge_labels parameter present (edge-label work); all binding-mode params present.
- artifact_authoring_guidance: target parameter present (pair-legality work);
  pair_guidance description phrase present; filter + diagram_type params present.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_write_tools() -> dict[str, object]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_write  # noqa: PLC0415

    return {t.name: t for t in mcp_write._tool_manager.list_tools()}  # type: ignore[attr-defined]


def _param_names(tool) -> set[str]:
    props = tool.parameters.get("properties", {})
    return set(props.keys())


# ---------------------------------------------------------------------------
# artifact_edit_diagram
# ---------------------------------------------------------------------------


class TestEditDiagramToolSchema:
    @pytest.fixture(scope="class")
    def tool(self):
        tools = _get_write_tools()
        assert "artifact_edit_diagram" in tools, "artifact_edit_diagram not registered"
        return tools["artifact_edit_diagram"]

    def test_edge_labels_parameter_present(self, tool) -> None:
        assert "edge_labels" in _param_names(tool), (
            "edge_labels parameter missing — T4 regression"
        )

    def test_edge_labels_schema_type(self, tool) -> None:
        edge_labels = tool.parameters["properties"]["edge_labels"]
        types = [v.get("type") for v in edge_labels.get("anyOf", [])]
        assert "object" in types and "null" in types, (
            "edge_labels must be nullable object (dict[str, str])"
        )

    def test_binding_mode_parameters_present(self, tool) -> None:
        params = _param_names(tool)
        for p in ("mode", "derivation_id", "diff", "base_revision", "entity_ids", "binding_id"):
            assert p in params, f"binding-mode param '{p}' missing"

    def test_core_frontmatter_parameters_present(self, tool) -> None:
        params = _param_names(tool)
        for p in ("artifact_id", "puml", "name", "keywords", "version", "status", "bindings"):
            assert p in params, f"frontmatter param '{p}' missing"

    def test_description_reflects_projection_aware_refresh(self, tool) -> None:
        desc = tool.description
        assert "projection-aware" in desc, (
            "Description must mention 'projection-aware' to reflect safe auto-sync dispatch"
        )
        assert "never deleted" in desc, (
            "Description must state scope-bound diagrams are never deleted on empty result"
        )

    def test_description_mentions_edge_labels(self, tool) -> None:
        desc = tool.description
        assert "edge_labels" in desc, (
            "Description must document the edge_labels parameter"
        )
        assert "edge-label" in desc or "edge_label" in desc, (
            "Description must explain what edge_labels does"
        )

    def test_description_mentions_binding_modes(self, tool) -> None:
        desc = tool.description
        for mode in ("refresh-derivation", "apply-diff", "propose-bindings", "detach-binding"):
            assert mode in desc, f"Binding mode '{mode}' missing from description"

    def test_viewpoint_parameter_present(self, tool) -> None:
        assert "viewpoint" in _param_names(tool), (
            "viewpoint parameter missing — WU-E6 regression"
        )

    def test_description_mentions_viewpoint(self, tool) -> None:
        desc = tool.description
        assert "viewpoint" in desc, "Description must document the viewpoint parameter"
        assert "ViewpointApplication" in desc, "Description must name the ViewpointApplication frontmatter"
        assert "viewpoint" in desc.split("Matrix diagrams")[1], (
            "Description must state viewpoint is rejected for matrix diagrams"
        )


# ---------------------------------------------------------------------------
# artifact_create_diagram
# ---------------------------------------------------------------------------


class TestCreateDiagramToolSchema:
    @pytest.fixture(scope="class")
    def tool(self):
        tools = _get_write_tools()
        assert "artifact_create_diagram" in tools, "artifact_create_diagram not registered"
        return tools["artifact_create_diagram"]

    def test_viewpoint_parameter_present(self, tool) -> None:
        assert "viewpoint" in _param_names(tool), (
            "viewpoint parameter missing — WU-E6 regression"
        )

    def test_description_mentions_viewpoint(self, tool) -> None:
        desc = tool.description
        assert "viewpoint" in desc, "Description must document the viewpoint parameter"
        assert "artifact_query_viewpoint" in desc, (
            "Description must point at artifact_query_viewpoint for viewpoint discovery"
        )


# ---------------------------------------------------------------------------
# artifact_authoring_guidance
# ---------------------------------------------------------------------------


class TestAuthoringGuidanceToolSchema:
    @pytest.fixture(scope="class")
    def tool(self):
        tools = _get_write_tools()
        assert "artifact_authoring_guidance" in tools, "artifact_authoring_guidance not registered"
        return tools["artifact_authoring_guidance"]

    def test_target_parameter_present(self, tool) -> None:
        assert "target" in _param_names(tool), (
            "target parameter missing — pair-legality regression"
        )

    def test_filter_and_diagram_type_parameters_present(self, tool) -> None:
        params = _param_names(tool)
        assert "filter" in params, "'filter' param missing"
        assert "diagram_type" in params, "'diagram_type' param missing"

    def test_description_mentions_pair_guidance(self, tool) -> None:
        desc = tool.description
        assert "pair_guidance" in desc or "pair-legality" in desc, (
            "Description must document pair-legality / pair_guidance capability"
        )

    def test_description_mentions_target_constraint(self, tool) -> None:
        desc = tool.description
        assert "target" in desc, "Description must mention the 'target' parameter"
        assert "filter" in desc, "Description must mention the 'filter' dependency"

    def test_description_covers_three_params(self, tool) -> None:
        desc = tool.description
        assert "diagram_type" in desc, "Description must cover diagram_type param"
        assert "filter" in desc, "Description must cover filter param"
        assert "target" in desc, "Description must cover target param"

    def test_description_directs_viewpoint_discovery_elsewhere(self, tool) -> None:
        """Authoring guidance is entity/connection/diagram-type only; viewpoint discovery
        belongs to the dedicated artifact_query_viewpoint tool, not this one."""
        desc = tool.description
        assert "artifact_query_viewpoint" in desc, (
            "Description must direct viewpoint discovery to artifact_query_viewpoint"
        )
