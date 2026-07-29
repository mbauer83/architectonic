"""Unit tests for the shared plain-language summary renderer."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding, QueryParameter
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_summary import (
    render_condition,
    render_connection_selection,
    render_derived_attribute,
    render_entity_group,
    render_incident,
    render_neighbor_inclusion,
    render_query_summary,
)
from src.domain.viewpoints.viewpoint_value_types import EntitySetType
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery


def _eq(attribute: str, value: object) -> AttributeCondition:
    return AttributeCondition(attribute=attribute, comparator="eq", value=ValueRef(literal=value))


def _type_condition(value: str) -> AttributeCondition:
    return _eq("type", value)


class TestConditionRendering:
    def test_eq(self) -> None:
        assert render_condition(_eq("type", "application-component")) == "type is application-component"

    def test_neq(self) -> None:
        condition = AttributeCondition(attribute="status", comparator="neq", value=ValueRef(literal="deprecated"))
        assert render_condition(condition) == "status is not deprecated"

    def test_in(self) -> None:
        condition = AttributeCondition(attribute="type", comparator="in", value=ValueRef(literal=["a", "b"]))
        assert render_condition(condition) == "type is one of a, b"

    def test_not_in(self) -> None:
        condition = AttributeCondition(attribute="type", comparator="not_in", value=ValueRef(literal=["a", "b"]))
        assert render_condition(condition) == "type is not one of a, b"

    def test_like(self) -> None:
        condition = AttributeCondition(attribute="name", comparator="like", value=ValueRef(literal="%Service"))
        assert render_condition(condition) == "name matches the pattern %Service"

    def test_ilike(self) -> None:
        condition = AttributeCondition(attribute="name", comparator="ilike", value=ValueRef(literal="%service%"))
        assert render_condition(condition) == "name matches the pattern %service% (case-insensitive)"

    def test_not_in_negate_wraps_in_not(self) -> None:
        condition = AttributeCondition(
            attribute="type", comparator="not_in", value=ValueRef(literal=["a", "b"]), negate=True
        )
        assert render_condition(condition) == "NOT (type is not one of a, b)"

    def test_exists(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="exists")
        assert render_condition(condition) == "risk_score is present"

    def test_absent(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="absent")
        assert render_condition(condition) == "risk_score has no value"

    def test_numeric_comparator_words(self) -> None:
        condition = AttributeCondition(attribute="strength", comparator="gte", value=ValueRef(literal=3))
        assert render_condition(condition) == "strength is at least 3"

    def test_eq_negate_uses_special_phrasing(self) -> None:
        """Eq + negate on a missing attribute still matches (strict complement) — the
        summary must read as inclusive of "no value", not a plain double-negative."""
        condition = AttributeCondition(
            attribute="status", comparator="eq", value=ValueRef(literal="deprecated"), negate=True
        )
        assert render_condition(condition) == "status is not deprecated, or has no value"

    def test_other_comparator_negate_wraps_in_not(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="gte", value=ValueRef(literal=7), negate=True)
        assert render_condition(condition) == "NOT (risk_score is at least 7)"

    def test_value_ref_attribute_of_self(self) -> None:
        condition = AttributeCondition(
            attribute="end_date", comparator="gte", value=ValueRef(kind="attribute_of_self", attribute="start_date")
        )
        assert render_condition(condition) == "end_date is at least its own start_date"

    def test_value_ref_attribute_of_endpoint(self) -> None:
        condition = AttributeCondition(
            attribute="strength",
            comparator="gte",
            value=ValueRef(kind="attribute_of_endpoint", endpoint="target", attribute="threshold"),
        )
        assert render_condition(condition) == "strength is at least the target entity's threshold"


class TestGroupRendering:
    def test_empty_root_group_is_match_all(self) -> None:
        assert render_entity_group(EntityCriteriaGroup()) == "any entity"

    def test_and_group_joins_with_and(self) -> None:
        group = EntityCriteriaGroup(children=(_eq("domain", "application"), _eq("status", "active")))
        assert render_entity_group(group) == "(domain is application and status is active)"

    def test_or_group_joins_with_or(self) -> None:
        group = EntityCriteriaGroup(
            conjunction="or", children=(_eq("domain", "application"), _eq("domain", "technology"))
        )
        assert render_entity_group(group) == "(domain is application or domain is technology)"

    def test_negated_group(self) -> None:
        group = EntityCriteriaGroup(children=(_eq("status", "deprecated"),), negate=True)
        assert render_entity_group(group) == "NOT (status is deprecated)"

    def test_nested_group(self) -> None:
        inner = EntityCriteriaGroup(
            conjunction="or", children=(_eq("domain", "application"), _eq("domain", "technology"))
        )
        negated_status = AttributeCondition(
            attribute="status", comparator="eq", value=ValueRef(literal="deprecated"), negate=True
        )
        outer = EntityCriteriaGroup(children=(inner, negated_status))
        rendered = render_entity_group(outer)
        assert rendered == (
            "((domain is application or domain is technology) and status is not deprecated, or has no value)"
        )

    def test_connection_group_empty(self) -> None:
        assert (
            render_connection_selection(ConnectionSelection())
            == "All connections between included entities are displayed"
        )


class TestIncidentRendering:
    def test_incident_with_direction_and_endpoint(self) -> None:
        condition = IncidentConnectionCondition(
            direction="outgoing",
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            endpoint_criteria=EntityCriteriaGroup(children=(_eq("type", "process"),)),
        )
        rendered = render_incident(condition)
        assert rendered == (
            "has a direct outgoing connection (type is archimate-serving) to an entity where (type is process)"
        )

    def test_negated_incident_states_the_excluded_union(self) -> None:
        """Incident negate is strict complement: the sentence names what is excluded,
        including the traversal — a negated ``both`` reads as excluding either kind."""
        condition = IncidentConnectionCondition(negate=True)
        assert render_incident(condition) == "has no direct connection (any) to an entity where (any entity)"
        negated_both = IncidentConnectionCondition(negate=True, traversal="both")
        assert render_incident(negated_both) == (
            "has no direct or derived connection (any) to an entity where (any entity)"
        )

    def test_any_connection_any_entity_defaults(self) -> None:
        condition = IncidentConnectionCondition()
        assert render_incident(condition) == "has a direct connection (any) to an entity where (any entity)"

    def test_each_traversal_reads_as_a_distinct_condition(self) -> None:
        rendered = {
            traversal: render_incident(IncidentConnectionCondition(direction="outgoing", traversal=traversal))
            for traversal in ("direct", "derived", "both")
        }
        assert rendered["direct"].startswith("has a direct outgoing connection")
        assert rendered["derived"].startswith("has a derived outgoing connection")
        assert rendered["both"].startswith("has a direct or derived outgoing connection")
        assert len(set(rendered.values())) == 3


class TestNeighborInclusionRendering:
    def test_default_inclusion(self) -> None:
        inclusion = NeighborInclusion()
        rendered = render_neighbor_inclusion(inclusion)
        assert rendered == (
            "Also include entities where (any entity) connected via a connection (any connection) "
            "to the primary selection"
        )

    def test_scoped_inclusion(self) -> None:
        inclusion = NeighborInclusion(
            direction="outgoing",
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            neighbor_criteria=EntityCriteriaGroup(
                children=(_eq("type", "process"), _eq("specialization", "business-process"))
            ),
        )
        rendered = render_neighbor_inclusion(inclusion)
        assert rendered == (
            "Also include entities where ((type is process and specialization is business-process)) "
            "connected via an outgoing connection (type is archimate-serving) to the primary selection"
        )

    def test_derived_inclusion_states_its_own_bound(self) -> None:
        """The hop bound in a derived-inclusion sentence comes from THIS inclusion's
        ``max_hops``, never from another clause's definition."""
        inclusion = NeighborInclusion(direction="incoming", traversal="derived", max_hops=4)
        rendered = render_neighbor_inclusion(inclusion)
        assert rendered == (
            "Also include entities where (any entity) connected via incoming derived relationships "
            "(any connection, up to 4 steps) to the primary selection"
        )

    def test_derived_inclusion_without_bound_uses_engine_default(self) -> None:
        inclusion = NeighborInclusion(traversal="derived")
        rendered = render_neighbor_inclusion(inclusion, default_max_hops=6)
        assert "(any connection, up to 6 steps)" in rendered

    def test_derived_inclusion_without_bound_or_default_names_the_limit(self) -> None:
        inclusion = NeighborInclusion(traversal="derived")
        rendered = render_neighbor_inclusion(inclusion)
        assert "(any connection, up to the configured hop limit)" in rendered

    def test_derived_inclusion_single_step_is_singular(self) -> None:
        inclusion = NeighborInclusion(traversal="derived", max_hops=1)
        assert "up to 1 step)" in render_neighbor_inclusion(inclusion)

    def test_derived_inclusion_discloses_potential_derivations(self) -> None:
        inclusion = NeighborInclusion(traversal="derived", max_hops=3, include_potential=True)
        rendered = render_neighbor_inclusion(inclusion)
        assert "(any connection, up to 3 steps, including potential derivations)" in rendered


class TestConnectionSelectionRendering:
    def test_disabled(self) -> None:
        assert render_connection_selection(ConnectionSelection(enabled=False)) == "No connections are displayed"

    def test_match_all(self) -> None:
        assert (
            render_connection_selection(ConnectionSelection())
            == "All connections between included entities are displayed"
        )

    def test_narrowed(self) -> None:
        criteria = ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),))
        selection = ConnectionSelection(criteria=criteria)
        assert render_connection_selection(selection) == "Connections are displayed where type is archimate-serving"


class TestFullQuerySummary:
    def test_matches_components_serving_processes_shape(self) -> None:
        """The renderer produces a coherent sentence set for a connected selection."""
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(
                    _eq("type", "application-component"),
                    IncidentConnectionCondition(
                        direction="outgoing",
                        connection_criteria=ConnectionCriteriaGroup(children=(_eq("type", "archimate-serving"),)),
                        endpoint_criteria=EntityCriteriaGroup(
                            children=(_eq("type", "process"), _eq("specialization", "business-process"))
                        ),
                    ),
                )
            ),
            include_connected=(
                NeighborInclusion(
                    direction="outgoing",
                    connection_criteria=ConnectionCriteriaGroup(children=(_eq("type", "archimate-serving"),)),
                    neighbor_criteria=EntityCriteriaGroup(
                        children=(_eq("type", "process"), _eq("specialization", "business-process"))
                    ),
                ),
            ),
        )
        summary = render_query_summary(query)
        assert summary.startswith(
            "Entity selection: (type is application-component and has a direct outgoing connection"
        )
        assert "Also include entities where" in summary
        assert (
            "All connections between included entities are displayed. "
            "Undirected connection types match direction filters in either direction."
        ) in summary

    def test_renders_parameter_binding_and_derived_attribute(self) -> None:
        query = ExecutableViewpointQuery(
            parameters=(QueryParameter("anchor", "entity-id"),),
            bindings=(
                QueryBinding(
                    "critical",
                    result_type=EntitySetType(frozenset()),
                    select="entities",
                    criteria=EntityCriteriaGroup(),
                ),
            ),
            derived=(DerivedAttribute("impact", direction="outgoing"),),
        )
        summary = render_query_summary(query)
        assert "Takes a required entity-id input ⟨anchor⟩." in summary
        assert "Let critical be entities where any entity." in summary
        assert "Derived impact: count connections for directly connected outgoing." in summary


class TestDerivedAttributeRendering:
    def test_derived_traversal_names_its_own_bound(self) -> None:
        attribute = DerivedAttribute(
            "impact-distance",
            direction="incoming",
            traversal="derived",
            max_hops=3,
            reduce="min",
            of="relationship.hops",
        )
        assert render_derived_attribute(attribute) == (
            "Derived impact-distance: min relationship.hops across incoming derived relationships (up to 3 steps)."
        )

    def test_derived_traversal_without_bound_uses_engine_default(self) -> None:
        attribute = DerivedAttribute("impact-distance", traversal="derived", reduce="min", of="relationship.hops")
        assert render_derived_attribute(attribute, default_max_hops=4) == (
            "Derived impact-distance: min relationship.hops across derived relationships (up to 4 steps)."
        )

    def test_derived_traversal_discloses_potential(self) -> None:
        attribute = DerivedAttribute("reach", traversal="derived", max_hops=2, include_potential=True)
        assert render_derived_attribute(attribute) == (
            "Derived reach: count connections across derived relationships "
            "(up to 2 steps, including potential derivations)."
        )


class TestClauseBoundIndependence:
    def test_each_clause_renders_its_own_hop_bound(self) -> None:
        """A query whose derived attribute and derived inclusion carry DIFFERENT bounds
        must render each number in its own sentence — never one clause's bound applied
        to another's."""
        query = ExecutableViewpointQuery(
            derived=(
                DerivedAttribute(
                    "impact-distance",
                    direction="incoming",
                    traversal="derived",
                    max_hops=2,
                    reduce="min",
                    of="relationship.hops",
                ),
            ),
            entity_criteria=EntityCriteriaGroup(children=(_eq("type", "application-component"),)),
            include_connected=(NeighborInclusion(direction="incoming", traversal="derived", max_hops=4),),
        )
        summary = render_query_summary(query, default_derivation_max_hops=9)
        assert (
            "Derived impact-distance: min relationship.hops across incoming derived relationships (up to 2 steps)."
        ) in summary
        assert "connected via incoming derived relationships (any connection, up to 4 steps)" in summary
        assert "9" not in summary

    def test_element_dependents_shape_regression(self) -> None:
        """The anchored dependents recipe: the inclusion's 4-step derived traversal and
        the attribute's default-bounded aggregation each read from their own clause."""
        query = ExecutableViewpointQuery(
            parameters=(QueryParameter("anchor", "entity-id"),),
            derived=(
                DerivedAttribute(
                    "impact-distance", direction="incoming", traversal="derived", reduce="min", of="relationship.hops"
                ),
            ),
            entity_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="id", comparator="eq", value=ValueRef(kind="parameter", parameter="anchor")
                    ),
                )
            ),
            include_connected=(NeighborInclusion(direction="incoming", traversal="derived", max_hops=4),),
        )
        summary = render_query_summary(query, default_derivation_max_hops=4)
        assert summary == (
            "Takes a required entity-id input ⟨anchor⟩. "
            "Derived impact-distance: min relationship.hops across incoming derived relationships (up to 4 steps). "
            "Entity selection: id is the supplied ⟨anchor⟩. "
            "Also include entities where (any entity) connected via incoming derived relationships "
            "(any connection, up to 4 steps) to the primary selection. "
            "All connections between included entities are displayed. "
            "Undirected connection types match direction filters in either direction."
        )


class TestSymmetricDirectionDisclosure:
    def test_directional_incident_predicate_appends_the_note(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(IncidentConnectionCondition(direction="outgoing"),),
            ),
        )
        assert render_query_summary(query).endswith(
            "Undirected connection types match direction filters in either direction."
        )

    def test_directional_predicate_nested_in_endpoint_criteria_appends_the_note(self) -> None:
        nested = IncidentConnectionCondition(
            endpoint_criteria=EntityCriteriaGroup(children=(IncidentConnectionCondition(direction="incoming"),))
        )
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(nested,)))
        assert "Undirected connection types" in render_query_summary(query)

    def test_direction_free_query_has_no_note(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_eq("type", "application-component"),)),
        )
        assert "Undirected connection types" not in render_query_summary(query)
