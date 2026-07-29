"""Aggregation contract for scale-adaptive presentation: identity includes endpoint
aggregates, homogeneity is structural, membership is conserved, and aggregation reads the
complete population."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_aggregation import (
    AggregateConnection,
    AggregateMember,
    aggregate_population,
    connection_provenance,
    resolve_aggregation_dimension,
)


def _member(entity_id: str, *, group: str, entity_type: str = "application-component") -> AggregateMember:
    return AggregateMember(entity_id=entity_id, entity_type=entity_type, group=group, domain="application")


def _connection(
    connection_id: str, source: str, target: str, *, certainty: str | None = None
) -> AggregateConnection:
    return AggregateConnection(
        connection_id=connection_id,
        source=source,
        target=target,
        connection_type="archimate-serving",
        certainty=certainty,  # type: ignore[arg-type]
    )


class TestNodeAggregation:
    def test_identity_is_dimension_value_and_entity_type(self) -> None:
        members = (
            _member("E1", group="platform-core"),
            _member("E2", group="platform-core"),
            _member("E3", group="platform-core", entity_type="application-service"),
            _member("E4", group="assurance"),
        )
        summary = aggregate_population(members, (), dimension="group", legibility_budget=100)
        identities = {(n.dimension_value, n.entity_type): n.member_count for n in summary.nodes}
        assert identities == {
            ("platform-core", "application-component"): 2,
            ("platform-core", "application-service"): 1,
            ("assurance", "application-component"): 1,
        }

    def test_membership_is_conserved(self) -> None:
        members = tuple(_member(f"E{i}", group=f"g{i % 3}") for i in range(120))
        summary = aggregate_population(members, (), dimension="group", legibility_budget=100)
        assert sum(node.member_count for node in summary.nodes) == 120
        all_ids = [entity_id for node in summary.nodes for entity_id in node.member_ids]
        assert len(all_ids) == len(set(all_ids)) == 120


class TestEdgeAggregation:
    def test_topology_preservation_same_type_different_pairs_stay_separate(self) -> None:
        members = (
            _member("core-1", group="platform-core"),
            _member("assurance-1", group="assurance"),
            _member("motivation-1", group="motivation-narrative"),
        )
        connections = (
            _connection("C1", "core-1", "assurance-1"),
            _connection("C2", "core-1", "motivation-1"),
        )
        summary = aggregate_population(members, connections, dimension="group", legibility_budget=100)
        assert len(summary.edges) == 2, "same-typed edges between DIFFERENT aggregate pairs must stay two bundles"
        targets = {edge.target_aggregate_id for edge in summary.edges}
        assert len(targets) == 2

    def test_no_aggregate_mixes_provenance_classes(self) -> None:
        members = (_member("A", group="g1"), _member("B", group="g2"))
        connections = (
            _connection("C1", "A", "B"),
            _connection("C2", "A", "B", certainty="certain"),
            _connection("C3", "A", "B", certainty="potential"),
        )
        summary = aggregate_population(members, connections, dimension="group", legibility_budget=100)
        assert len(summary.edges) == 3
        assert {edge.provenance for edge in summary.edges} == {"modeled", "derived-certain", "derived-potential"}
        assert all(edge.member_count == 1 for edge in summary.edges)

    def test_direction_is_part_of_edge_identity(self) -> None:
        members = (_member("A", group="g1"), _member("B", group="g2"))
        connections = (_connection("C1", "A", "B"), _connection("C2", "B", "A"))
        summary = aggregate_population(members, connections, dimension="group", legibility_budget=100)
        assert len(summary.edges) == 2

    def test_edge_membership_is_conserved_within_the_aggregated_population(self) -> None:
        members = (_member("A", group="g1"), _member("B", group="g2"), _member("C", group="g2"))
        connections = tuple(_connection(f"C{i}", "A", "B") for i in range(5)) + (
            _connection("C9", "A", "C"),
        )
        summary = aggregate_population(members, connections, dimension="group", legibility_budget=100)
        assert sum(edge.member_count for edge in summary.edges) == 6


class TestDimensionResolution:
    def test_explicit_aggregate_by_wins_then_group_by_then_group(self) -> None:
        assert resolve_aggregation_dimension("domain", "type") == "domain"
        assert resolve_aggregation_dimension(None, "type") == "type"
        assert resolve_aggregation_dimension(None, "specialization") == "group"
        assert resolve_aggregation_dimension(None, None) == "group"

    def test_provenance_classes(self) -> None:
        assert connection_provenance(None) == "modeled"
        assert connection_provenance("certain") == "derived-certain"
        assert connection_provenance("potential") == "derived-potential"
