"""Unit tests for the repository-context projection (companion plan §6.1): Appendix-C
"Projection" cluster, repository half — only matches present, styled, deterministic order.
"""

from __future__ import annotations

import pytest

from src.application.viewpoints.repository_projection import project_repository
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    EntityCriteriaGroup,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoints import (
    ColumnSpec,
    ExecutableViewpointQuery,
    PresentationSpec,
    StyleRule,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES, Store, connection, entity


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test-viewpoint", version=1, name="Test")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


class TestNoQuery:
    def test_definition_without_query_returns_empty_projection(self) -> None:
        definition = _definition()
        projection = project_repository(definition, read_access=Store(), registries=REGISTRIES)
        assert projection.target == "repository"
        assert projection.items == ()


class TestOnlyMatchesPresent:
    def test_non_matching_entities_are_absent(self) -> None:
        store = Store(
            entities={
                "ENT@match": entity(artifact_id="ENT@match", artifact_type="application-component"),
                "ENT@nomatch": entity(artifact_id="ENT@nomatch", artifact_type="process"),
            }
        )
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),))
        )
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        ids = {item.item_id for item in projection.items}
        assert ids == {"ENT@match"}
        assert all(item.state == "visible" and item.reasons == () for item in projection.items)


class TestStyling:
    @pytest.mark.verifies("REQ@1783870981.mdH8Uv")
    def test_matching_entities_are_styled(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A", status="deprecated")})
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(
                    capability="badges",
                    mode="match",
                    match_criteria=EntityCriteriaGroup(
                        children=(
                            AttributeCondition(
                                attribute="status", comparator="eq", value=ValueRef(literal="deprecated")
                            ),
                        )
                    ),
                    value="badge-warning",
                ),
            ),
        )
        definition = _definition(query=query, presentation=presentation)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        assert projection.items[0].style == {"badges": "badge-warning"}


class TestRuleOutcomes:
    """Every authored style rule reports exactly one observable outcome — never a
    silent no-op."""

    def _match_rule(self, capability: str, status: str, value: str) -> StyleRule:
        return StyleRule(
            capability=capability,
            mode="match",
            match_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal=status)),)
            ),
            value=value,
        )

    def _project(self, presentation: PresentationSpec, *, store: Store | None = None):
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        definition = _definition(query=query, presentation=presentation)
        effective_store = store if store is not None else Store(
            entities={"ENT@A": entity(artifact_id="ENT@A", status="deprecated")}
        )
        return project_repository(definition, read_access=effective_store, registries=REGISTRIES)

    def test_applied_rule_reports_its_count(self) -> None:
        projection = self._project(
            PresentationSpec(representation="table", styling_rules=(self._match_rule("badges", "deprecated", "x"),))
        )
        (outcome,) = projection.rule_outcomes
        assert (outcome.kind, outcome.applied_count, outcome.matched_count) == ("applied", 1, 1)
        assert not any("style rule" in warning for warning in projection.warnings)

    def test_valid_rule_with_zero_matches_is_expected_empty_and_never_warns(self) -> None:
        projection = self._project(
            PresentationSpec(representation="table", styling_rules=(self._match_rule("badges", "retired", "x"),))
        )
        (outcome,) = projection.rule_outcomes
        assert outcome.kind == "expected-empty"
        assert outcome.matched_count == 0
        assert not any("style rule" in warning for warning in projection.warnings)

    def test_fully_shadowed_rule_reports_shadowed_and_warns(self) -> None:
        projection = self._project(
            PresentationSpec(
                representation="table",
                styling_rules=(
                    self._match_rule("badges", "deprecated", "first"),
                    self._match_rule("badges", "deprecated", "second"),
                ),
            )
        )
        first, second = projection.rule_outcomes
        assert first.kind == "applied"
        assert second.kind == "shadowed"
        assert second.matched_count == 1
        assert second.applied_count == 0
        assert any(
            "style rule 2 (badges)" in warning and "higher-precedence" in warning for warning in projection.warnings
        )

    def test_scale_rule_with_undeclared_derived_attribute_is_unresolvable_and_warns(self) -> None:
        projection = self._project(
            PresentationSpec(
                representation="exploration",
                styling_rules=(
                    StyleRule(
                        capability="node_color",
                        mode="scale",
                        scale_attribute="derived.conn_count",
                        scale_tokens=("heat-near", "heat-far"),
                    ),
                ),
            )
        )
        (outcome,) = projection.rule_outcomes
        assert outcome.kind == "unresolvable"
        assert outcome.detail == "derived.conn_count"
        assert any("derived.conn_count" in warning and "cannot resolve" in warning for warning in projection.warnings)


class TestColumnValues:
    def test_authored_columns_are_resolved_server_side_with_explicit_missing_marks(self) -> None:
        store = Store(
            entities={
                "ENT@A": entity(artifact_id="ENT@A", status="draft", extra={"criticality": "high"}),
                "ENT@B": entity(artifact_id="ENT@B", status="active"),
            }
        )
        presentation = PresentationSpec(
            representation="table",
            columns=(ColumnSpec(label="Status", source="status"), ColumnSpec(label="Crit", source="criticality")),
        )
        definition = _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()), presentation=presentation
        )
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        values = {item.item_id: item.column_values for item in projection.items}
        assert values["ENT@A"] == {"status": "draft", "criticality": "high"}
        assert values["ENT@B"] == {"status": "active", "criticality": None}

    def test_no_authored_columns_means_no_column_values(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        assert all(item.column_values is None for item in projection.items)


class TestDeterministicOrder:
    def test_entity_ids_are_sorted(self) -> None:
        store = Store(entities={"ENT@C": entity(artifact_id="ENT@C"), "ENT@A": entity(artifact_id="ENT@A")})
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        ids = [item.item_id for item in projection.items]
        assert ids == sorted(ids)


class TestMembership:
    def test_expanded_membership_from_neighbor_inclusion(self) -> None:
        primary = entity(artifact_id="ENT@primary", artifact_type="application-component")
        neighbor = entity(artifact_id="ENT@neighbor", artifact_type="process")
        link = connection(artifact_id="CON@1", source="ENT@primary", target="ENT@neighbor")
        store = Store(entities={"ENT@primary": primary, "ENT@neighbor": neighbor}, connections=[link])
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),)),
            include_connected=(NeighborInclusion(),),
        )
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        by_id = {item.item_id: item for item in projection.items if item.item_kind == "entity"}
        assert by_id["ENT@primary"].membership == "primary"
        assert by_id["ENT@neighbor"].membership == "expanded"


class TestRepoScope:
    def _store(self) -> Store:
        return Store(
            entities={
                "ENT@enterprise": entity(artifact_id="ENT@enterprise"),
                "ENT@engagement": entity(artifact_id="ENT@engagement"),
            },
            enterprise_ids=frozenset({"ENT@enterprise"}),
        )

    def test_enterprise_scope(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(), repo_scope="enterprise")
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=self._store(), registries=REGISTRIES)
        assert {item.item_id for item in projection.items} == {"ENT@enterprise"}

    def test_engagement_scope(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(), repo_scope="engagement")
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=self._store(), registries=REGISTRIES)
        assert {item.item_id for item in projection.items} == {"ENT@engagement"}

    def test_both_scope(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(), repo_scope="both")
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=self._store(), registries=REGISTRIES)
        assert {item.item_id for item in projection.items} == {"ENT@enterprise", "ENT@engagement"}


class TestSchemaDrift:
    def test_drift_surfaces_as_warning(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="unknown_field", comparator="exists"),)
            )
        )
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        assert projection.items == ()
        assert any("unknown_field" in warning for warning in projection.warnings)


class TestConnectionsIncluded:
    def test_connection_between_matched_entities_is_included(self) -> None:
        entity_a = entity(artifact_id="ENT@A")
        entity_b = entity(artifact_id="ENT@B")
        link = connection(artifact_id="CON@ab", source="ENT@A", target="ENT@B")
        store = Store(entities={"ENT@A": entity_a, "ENT@B": entity_b}, connections=[link])
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        definition = _definition(query=query)
        projection = project_repository(definition, read_access=store, registries=REGISTRIES)
        connection_items = [item for item in projection.items if item.item_kind == "connection"]
        assert {item.item_id for item in connection_items} == {"CON@ab"}
