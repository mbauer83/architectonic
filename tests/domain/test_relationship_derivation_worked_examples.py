"""Executable relationship-derivation examples."""

from __future__ import annotations

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.ontologies.archimate_4 import module
from tests.fixtures.viewpoints.derivation_examples import (
    ExampleGraph,
    catalog,
    financial_application,
    flow_endpoints,
    hosting_suite,
    project_specialization,
    sales_and_shipping,
)


def _derive(
    graph: ExampleGraph, anchors: frozenset[str], *, hops: int, potential: bool = False
) -> set[tuple[str, str, str, str]]:
    result = derive_relationships(
        RelationshipDerivationRequest(
            anchors,
            "outgoing",
            "include_potential" if potential else "certain_only",
            DerivationBounds(hops, 100),
        ),
        read_access=graph,
        registries=catalog(),
    )
    return {(item.source_id, item.target_id, item.connection_type, item.certainty) for item in result.relationships}


def test_financial_application_derives_indirect_realization_without_direct_permission() -> None:
    graph = financial_application()

    assert module.permitted_relationships.permits(
        EntityTypeName("application-component"),
        EntityTypeName("service"),
        ConnectionTypeName("archimate-realization"),
    ) is False
    assert _derive(graph, frozenset({"financial-application"}), hops=3) == {
        ("financial-application", "payment-subfunction", "archimate-assignment", "certain"),
        ("financial-application", "payment-service", "archimate-realization", "certain"),
    }


def test_flow_relationship_transfers_across_both_service_endpoints() -> None:
    assert _derive(flow_endpoints(), frozenset({"source-function", "source-service"}), hops=3) == {
        ("source-function", "target-service", "archimate-flow", "certain"),
        ("source-service", "target-function", "archimate-flow", "certain"),
    }


def test_sales_department_triggers_shipping_and_aggregated_billing() -> None:
    assert _derive(sales_and_shipping(), frozenset({"sales-department"}), hops=3) == {
        ("sales-department", "invoicing", "archimate-triggering", "certain"),
        ("sales-department", "billing", "archimate-triggering", "certain"),
        ("sales-department", "payment", "archimate-triggering", "certain"),
        ("sales-department", "shipping", "archimate-triggering", "certain"),
    }


def test_hosting_candidates_are_potential_when_suite_is_detailed() -> None:
    assert _derive(
        hosting_suite(),
        frozenset({"database-hosting", "website-hosting"}),
        hops=2,
        potential=True,
    ) == {
        ("database-hosting", "front-end", "archimate-serving", "potential"),
        ("database-hosting", "back-end", "archimate-serving", "potential"),
        ("website-hosting", "front-end", "archimate-serving", "potential"),
        ("website-hosting", "back-end", "archimate-serving", "potential"),
    }


def test_specialization_examples_produce_the_stated_potential_relationships() -> None:
    assert _derive(
        project_specialization(),
        frozenset({"it-project-team", "project-team", "it-project", "project"}),
        hops=2,
        potential=True,
    ) == {
        ("it-project-team", "project", "archimate-assignment", "potential"),
        ("project-team", "it-project", "archimate-assignment", "potential"),
        ("it-project-team", "project-manager", "archimate-aggregation", "potential"),
        ("it-project", "project-planning", "archimate-access", "potential"),
        ("project", "software-documentation", "archimate-access", "potential"),
        ("project-team", "project-planning", "archimate-access", "certain"),
    }
