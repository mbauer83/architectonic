"""Tests for viewpoint definitions/applications and structural parsing."""

from __future__ import annotations

from typing import Any

import pytest

from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoints import (
    ViewpointApplication,
    ViewpointCatalog,
    ViewpointDefinition,
)


class TestViewpointCatalog:
    def test_duplicate_slug_raises(self) -> None:
        defn = ViewpointDefinition(slug="dup", version=1, name="Dup")
        with pytest.raises(ValueError, match="Duplicate viewpoint slug"):
            ViewpointCatalog((defn, defn))

    def test_or_merges_catalogs(self) -> None:
        left = ViewpointCatalog((ViewpointDefinition(slug="a", version=1, name="A"),))
        right = ViewpointCatalog((ViewpointDefinition(slug="b", version=1, name="B"),))
        merged = left | right
        assert merged.get("a") is not None
        assert merged.get("b") is not None

    def test_empty_catalog_get_returns_none(self) -> None:
        assert ViewpointCatalog.empty().get("missing") is None


class TestViewpointApplication:
    def test_construction(self) -> None:
        application = ViewpointApplication(
            target_kind="diagram",
            target_id="DGM@1.abc.example",
            viewpoint_slug="motivation",
            pinned_version=1,
        )
        assert application.enforcement_override is None
        assert application.derivation_params == {}


class TestViewpointCatalogFromMapping:
    def test_missing_viewpoints_key_is_empty_catalog(self) -> None:
        assert viewpoint_catalog_from_mapping({}) == ViewpointCatalog.empty()

    def test_parses_basic_fields_and_scope(self) -> None:
        catalog = viewpoint_catalog_from_mapping(
            {
                "viewpoints": [
                    {
                        "slug": "motivation",
                        "version": 3,
                        "name": "Motivation",
                        "purpose": "deciding",
                        "content": "coherence",
                        "stakeholders": ["enterprise-architects"],
                        "concerns": ["why are we doing this"],
                        "scope": {"entity_types": ["stakeholder", "driver"]},
                        "representation_types": ["archimate-motivation"],
                    }
                ]
            }
        )
        definition = catalog.get("motivation")
        assert definition is not None
        assert definition.version == 3
        assert definition.purpose == ("deciding",)
        assert definition.content == ("coherence",)
        assert definition.scope.entity_types == frozenset({"stakeholder", "driver"})
        assert definition.representation_types == ("archimate-motivation",)

    def test_version_field_round_trips(self) -> None:
        catalog = viewpoint_catalog_from_mapping({"viewpoints": [{"slug": "v", "version": 7, "name": "V"}]})
        definition = catalog.get("v")
        assert definition is not None
        assert definition.version == 7

    def test_invalid_purpose_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="purpose"):
            viewpoint_catalog_from_mapping(
                {"viewpoints": [{"slug": "v", "version": 1, "name": "V", "purpose": "not-a-purpose"}]}
            )

    def test_invalid_content_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="content"):
            viewpoint_catalog_from_mapping(
                {"viewpoints": [{"slug": "v", "version": 1, "name": "V", "content": "not-a-content"}]}
            )

    def test_unknown_top_level_key_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="unknown key"):
            viewpoint_catalog_from_mapping({"viewpoints": [{"slug": "v", "version": 1, "name": "V", "bogus": True}]})


class TestPurposeContentCardinality:
    def test_purpose_list_shorthand_parses_multiple_values(self) -> None:
        catalog = viewpoint_catalog_from_mapping(
            {"viewpoints": [{"slug": "v", "version": 1, "name": "V", "purpose": ["designing", "deciding"]}]}
        )
        definition = catalog.get("v")
        assert definition is not None
        assert definition.purpose == ("designing", "deciding")

    def test_content_list_shorthand_parses_multiple_values(self) -> None:
        catalog = viewpoint_catalog_from_mapping(
            {"viewpoints": [{"slug": "v", "version": 1, "name": "V", "content": ["details", "overview"]}]}
        )
        definition = catalog.get("v")
        assert definition is not None
        assert definition.content == ("details", "overview")

    def test_absent_purpose_content_default_to_single_element_tuples(self) -> None:
        catalog = viewpoint_catalog_from_mapping({"viewpoints": [{"slug": "v", "version": 1, "name": "V"}]})
        definition = catalog.get("v")
        assert definition is not None
        assert definition.purpose == ("informing",)
        assert definition.content == ("overview",)


class TestQueryShapeParsing:
    def _query_mapping(self) -> dict[str, Any]:
        return {
            "slug": "filtered",
            "version": 1,
            "name": "Filtered",
            "query": {
                "query_schema": 1,
                "entity_criteria": {
                    "kind": "group",
                    "conjunction": "and",
                    "children": [
                        {
                            "kind": "condition",
                            "attribute": "specialization",
                            "comparator": "eq",
                            "value": "business-service",
                        },
                        {"kind": "condition", "attribute": "criticality", "comparator": "eq", "value": "high"},
                    ],
                },
                "connections": {
                    "criteria": {
                        "kind": "group",
                        "conjunction": "and",
                        "children": [
                            {"kind": "condition", "attribute": "type", "comparator": "eq", "value": "archimate-serving"}
                        ],
                    }
                },
                "repo_scope": "engagement",
            },
        }

    def test_parses_query_shape(self) -> None:
        catalog = viewpoint_catalog_from_mapping({"viewpoints": [self._query_mapping()]})
        definition = catalog.get("filtered")
        assert definition is not None
        query = definition.query
        assert query is not None
        assert len(query.entity_criteria.children) == 2
        first_criterion = query.connections.criteria.children[0]
        assert first_criterion.attribute == "type"  # type: ignore[union-attr]
        assert query.repo_scope == "engagement"

    def test_invalid_query_schema_version_rejected_loudly(self) -> None:
        mapping = self._query_mapping()
        mapping["query"]["query_schema"] = 2
        with pytest.raises(ValueError, match="query_schema"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})

    def test_query_schema_is_required(self) -> None:
        mapping = self._query_mapping()
        del mapping["query"]["query_schema"]
        with pytest.raises(ValueError, match="query_schema is required"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})

    def test_empty_ad_hoc_query_normalizes_to_current_schema(self) -> None:
        catalog = viewpoint_catalog_from_mapping(
            {"viewpoints": [{"slug": "ad-hoc", "version": 1, "name": "Ad hoc", "query": {}}]}
        )
        definition = catalog.get("ad-hoc")
        assert definition is not None
        assert definition.query is not None
        assert definition.query.query_schema == 1

    def test_invalid_comparator_rejected_loudly(self) -> None:
        mapping = self._query_mapping()
        mapping["query"]["entity_criteria"]["children"][0]["comparator"] = "matches"
        with pytest.raises(ValueError, match="comparator"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})

    def test_invalid_repo_scope_rejected_loudly(self) -> None:
        mapping = self._query_mapping()
        mapping["query"]["repo_scope"] = "everywhere"
        with pytest.raises(ValueError, match="repo_scope"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})

    def test_unknown_key_in_criteria_node_rejected_loudly(self) -> None:
        mapping = self._query_mapping()
        mapping["query"]["entity_criteria"]["children"][0]["bogus"] = True
        with pytest.raises(ValueError, match="unknown key"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})


class TestPresentationShapeParsing:
    def _presentation_mapping(self) -> dict[str, Any]:
        return {
            "slug": "styled",
            "version": 1,
            "name": "Styled",
            "presentation": {
                "representation": "exploration",
                "display_options": {"cluster_grouping": True},
                "group_by": "type",
                "styling_rules": [
                    {
                        "capability": "node_color",
                        "mode": "match",
                        "match_criteria": {
                            "kind": "group",
                            "conjunction": "and",
                            "children": [
                                {"kind": "condition", "attribute": "status", "comparator": "eq", "value": "active"}
                            ],
                        },
                        "value": "token-green",
                    }
                ],
            },
        }

    def test_parses_presentation_shape(self) -> None:
        catalog = viewpoint_catalog_from_mapping({"viewpoints": [self._presentation_mapping()]})
        definition = catalog.get("styled")
        assert definition is not None
        presentation = definition.presentation
        assert presentation is not None
        assert presentation.representation == "exploration"
        assert presentation.display_options == {"cluster_grouping": True}
        assert presentation.group_by == "type"
        assert presentation.styling_rules[0].capability == "node_color"
        assert presentation.styling_rules[0].value == "token-green"

    def test_invalid_representation_rejected_loudly(self) -> None:
        mapping = self._presentation_mapping()
        mapping["presentation"]["representation"] = "graph"
        with pytest.raises(ValueError, match="representation"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})

    def test_invalid_style_rule_mode_rejected_loudly(self) -> None:
        mapping = self._presentation_mapping()
        mapping["presentation"]["styling_rules"][0]["mode"] = "vibes"
        with pytest.raises(ValueError, match="mode"):
            viewpoint_catalog_from_mapping({"viewpoints": [mapping]})
