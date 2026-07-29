"""Selection-mode semantics: layer classification, schema round-trip, and the
informational divergence code (never blocking)."""

from __future__ import annotations

import pytest

from src.domain.concept_scope import ConceptScope
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.domain.viewpoints.viewpoint_scope_query import classify_selection_layers, query_from_scope
from src.domain.viewpoints.viewpoint_serialization import viewpoint_definition_to_mapping
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointDefinition


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test", version=1, name="Test")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


_SCOPE = ConceptScope(entity_types=frozenset({"goal", "process"}))


class TestClassifySelectionLayers:
    def test_scope_only(self) -> None:
        assert classify_selection_layers(_definition(scope=_SCOPE)) == "scope-only"

    def test_query_only(self) -> None:
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        assert classify_selection_layers(definition) == "query-only"

    def test_dual_equivalent_is_the_scopes_mechanical_translation(self) -> None:
        definition = _definition(scope=_SCOPE, query=query_from_scope(_SCOPE))
        assert classify_selection_layers(definition) == "dual-equivalent"

    def test_dual_divergent_when_the_query_says_anything_else(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="goal")),)
            )
        )
        assert classify_selection_layers(_definition(scope=_SCOPE, query=query)) == "dual-divergent"


class TestSchemaRoundTrip:
    def test_selection_mode_round_trips_and_is_omitted_when_unset(self) -> None:
        stamped = _definition(scope=_SCOPE, selection_mode="scope")
        mapped = viewpoint_definition_to_mapping(stamped)
        assert mapped["selection_mode"] == "scope"
        assert viewpoint_definition_from_mapping(mapped).selection_mode == "scope"

        legacy = viewpoint_definition_to_mapping(_definition(scope=_SCOPE))
        assert "selection_mode" not in legacy
        assert viewpoint_definition_from_mapping(legacy).selection_mode is None

    def test_unknown_selection_mode_is_a_parse_error(self) -> None:
        with pytest.raises(ValueError, match="selection_mode"):
            viewpoint_definition_from_mapping({"slug": "x", "selection_mode": "banana"})


class TestDivergenceCode:
    def _issues(self, definition: ViewpointDefinition):
        return validate_viewpoint_definition(
            definition,
            mode="persist_edit",
            known_entity_types=frozenset({"goal", "process"}),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
        )

    def test_divergent_layers_yield_an_informational_warning_only(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        issues = self._issues(_definition(scope=_SCOPE, query=query, selection_mode="scope"))
        divergence = [issue for issue in issues if issue.code == "selection-layers-diverge"]
        assert len(divergence) == 1
        assert divergence[0].severity == "warning"
        assert "scope layer is active" in divergence[0].message
        assert not any(issue.severity == "error" for issue in issues)

    def test_equivalent_layers_and_single_layer_definitions_stay_silent(self) -> None:
        for definition in (
            _definition(scope=_SCOPE, query=query_from_scope(_SCOPE), selection_mode="query"),
            _definition(scope=_SCOPE, selection_mode="scope"),
        ):
            assert not any(issue.code == "selection-layers-diverge" for issue in self._issues(definition))
