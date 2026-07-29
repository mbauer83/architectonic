"""Tests for the viewpoint scope summary shown on guidance/enumeration surfaces."""

from __future__ import annotations

from src.domain.concept_scope import ConceptScope, HierarchyPredicate
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.infrastructure.write.artifact_write.viewpoint_type_guidance import summarize_scope


class TestSummarizeScope:
    def test_unrestricted_scope_summarizes_as_unrestricted(self) -> None:
        assert summarize_scope(ConceptScope.unrestricted()) == {"unrestricted": True}

    def test_entity_and_connection_allow_lists_are_summarized(self) -> None:
        scope = ConceptScope(
            entity_types=frozenset({EntityTypeName("goal")}),
            connection_types=frozenset({ConnectionTypeName("archimate-serving")}),
        )
        summary = summarize_scope(scope)
        assert summary == {
            "unrestricted": False, "entity_types": ["goal"], "connection_types": ["archimate-serving"],
        }

    def test_excluded_entity_and_connection_types_are_summarized(self) -> None:
        scope = ConceptScope(
            excluded_entity_types=frozenset({EntityTypeName("assessment")}),
            excluded_connection_types=frozenset({ConnectionTypeName("archimate-association")}),
        )
        summary = summarize_scope(scope)
        assert summary["excluded_entity_types"] == ["assessment"]
        assert summary["excluded_connection_types"] == ["archimate-association"]

    def test_excluded_domain_is_summarized(self) -> None:
        scope = ConceptScope(
            excluded_hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"assurance"})),)
        )
        summary = summarize_scope(scope)
        assert summary["excluded_domains"] == ["assurance"]

    def test_scope_with_only_exclusions_is_not_reported_as_unrestricted(self) -> None:
        scope = ConceptScope(excluded_entity_types=frozenset({EntityTypeName("assessment")}))
        summary = summarize_scope(scope)
        assert summary["unrestricted"] is False
