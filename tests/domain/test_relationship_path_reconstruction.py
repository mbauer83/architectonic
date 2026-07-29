"""Reconstruction behavior for relationship-derivation witness paths."""

from __future__ import annotations

from dataclasses import replace

from src.domain.relationships.relationship_path_reconstruction import (
    BrokenRelationshipPath,
    DerivedPathRelationship,
    NoLongerDerivedRelationship,
)
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    RelationshipDerivationRequest,
    derive_relationship_for_path,
    derive_relationships,
)
from tests.fixtures.viewpoints.derivation_examples import (
    ExampleGraph,
    catalog,
    financial_application,
    project_specialization,
)


def _financial_path() -> tuple[ExampleGraph, str]:
    graph = financial_application()
    result = derive_relationships(
        RelationshipDerivationRequest(
            frozenset({"financial-application"}), "outgoing", "certain_only", DerivationBounds(3, 20)
        ),
        read_access=graph,
        registries=catalog(),
    )
    relationship = next(item for item in result.relationships if item.target_id == "payment-service")
    return graph, relationship.path_key


def test_every_emitted_path_reconstructs_to_the_same_derived_relationship() -> None:
    graph = financial_application()
    result = derive_relationships(
        RelationshipDerivationRequest(
            frozenset({"financial-application"}), "outgoing", "certain_only", DerivationBounds(3, 20)
        ),
        read_access=graph,
        registries=catalog(),
    )

    for relationship in result.relationships:
        assert derive_relationship_for_path(relationship.path_key, read_access=graph, registries=catalog()) == (
            DerivedPathRelationship(
                relationship.source_id,
                relationship.target_id,
                relationship.connection_type,
                relationship.certainty,
                relationship.hops,
            )
        )


def test_missing_connection_and_dangling_endpoint_break_reconstruction() -> None:
    graph, path_key = _financial_path()
    graph.connections.pop()

    assert isinstance(
        derive_relationship_for_path(path_key, read_access=graph, registries=catalog()), BrokenRelationshipPath
    )

    graph, path_key = _financial_path()
    del graph.entities["payment-service"]

    assert isinstance(
        derive_relationship_for_path(path_key, read_access=graph, registries=catalog()), BrokenRelationshipPath
    )


def test_orientation_that_cannot_join_the_recorded_chain_is_broken() -> None:
    graph, _ = _financial_path()

    outcome = derive_relationship_for_path(
        "assigns-function@rev|realizes-service@fwd", read_access=graph, registries=catalog()
    )

    assert isinstance(outcome, BrokenRelationshipPath)


def test_retyped_connection_and_new_restriction_make_a_path_no_longer_derive() -> None:
    graph, path_key = _financial_path()
    graph.connections[1] = replace(graph.connections[1], conn_type="archimate-specialization")

    assert isinstance(
        derive_relationship_for_path(path_key, read_access=graph, registries=catalog()), NoLongerDerivedRelationship
    )

    graph, path_key = _financial_path()
    graph.entities["financial-application"] = replace(graph.entities["financial-application"], artifact_type="goal")

    assert isinstance(
        derive_relationship_for_path(path_key, read_access=graph, registries=catalog()), NoLongerDerivedRelationship
    )


def test_reconstruction_reports_a_changed_certainty() -> None:
    graph = project_specialization()
    path_key = "team-specialization@fwd|team-assignment@fwd"

    initial = derive_relationship_for_path(path_key, read_access=graph, registries=catalog())
    graph.connections[0] = replace(graph.connections[0], conn_type="archimate-assignment")
    changed = derive_relationship_for_path(path_key, read_access=graph, registries=catalog())

    assert isinstance(initial, DerivedPathRelationship)
    assert initial.certainty == "potential"
    assert isinstance(changed, DerivedPathRelationship)
    assert changed.certainty == "certain"
