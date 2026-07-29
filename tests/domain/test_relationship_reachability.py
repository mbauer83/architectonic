"""Bounded enumeration of ephemeral derived relationships."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.domain.modules.module_catalog import ModuleCatalogBuilder
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivationLimitError,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.viewpoint_criteria import IncidentDirection
from src.ontologies.archimate_4 import module


def _entity(identifier: str, type_name: str = "application-component") -> EntityRecord:
    return EntityRecord(
        artifact_id=identifier,
        artifact_type=type_name,
        name=identifier,
        version="1",
        status="draft",
        domain="application",
        subdomain="",
        path=Path("/entity"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="",
        display_alias="",
    )


def _connection(identifier: str, source: str, target: str, type_name: str) -> ConnectionRecord:
    return ConnectionRecord(identifier, source, target, type_name, "1", "draft", Path("/connection"), {}, "")


@dataclass
class _Graph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(
        self, entity_id: str, *, direction: str = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        return [connection for connection in self.connections if entity_id in {connection.source, connection.target}]


def _catalog():
    builder = ModuleCatalogBuilder()
    builder.register_ontology(module)
    return builder.build()


def _request(
    anchors: frozenset[str],
    direction: IncidentDirection = "either",
    *,
    hops: int = 3,
    limit: int = 20,
    potential: bool = False,
) -> RelationshipDerivationRequest:
    return RelationshipDerivationRequest(
        anchors,
        direction,
        "include_potential" if potential else "certain_only",
        DerivationBounds(hops, limit),
    )


def test_reachability_prefers_the_lexicographically_first_minimal_witness() -> None:
    graph = _Graph(
        {identifier: _entity(identifier) for identifier in ("A", "B", "C")},
        [
            _connection("CON@b", "A", "B", "archimate-assignment"),
            _connection("CON@a", "A", "B", "archimate-assignment"),
            _connection("CON@c", "B", "C", "archimate-realization"),
        ],
    )

    result = derive_relationships(_request(frozenset({"A"}), "outgoing"), read_access=graph, registries=_catalog())

    assert len(result.relationships) == 1
    relationship = result.relationships[0]
    assert relationship.connection_type == "archimate-realization"
    assert relationship.certainty == "certain"
    assert relationship.hops == 2
    assert relationship.path_key == "CON@a@fwd|CON@c@fwd"
    assert relationship.artifact_id == "derived::archimate-realization::CON@a@fwd|CON@c@fwd"


def test_reachability_collapses_multiple_composed_types_between_the_same_pair_to_one() -> None:
    # Two independent, equally-valid 2-hop compositions between A and C, each producing a
    # DIFFERENT connection type (DR1: specialization+specialization -> specialization;
    # DR2: structural+structural -> weakest(assignment, assignment) = assignment) — a real
    # pair of entities can be composable through more than one intermediate chain, but only
    # the single best-evidenced relationship should be reported, not one per alternate type.
    graph = _Graph(
        {identifier: _entity(identifier) for identifier in ("A", "B", "C", "X", "Y")},
        [
            _connection("CON@a1", "A", "X", "archimate-assignment"),
            _connection("CON@a2", "X", "C", "archimate-assignment"),
            _connection("CON@b1", "A", "Y", "archimate-specialization"),
            _connection("CON@b2", "Y", "C", "archimate-specialization"),
        ],
    )

    result = derive_relationships(_request(frozenset({"A"}), "outgoing"), read_access=graph, registries=_catalog())

    pairs = {(r.source_id, r.target_id) for r in result.relationships}
    assert pairs == {("A", "C")}, "expected exactly one relationship for the A-C pair, not one per composed type"
    assert len(result.relationships) == 1
    # Deterministic tiebreak: both candidates are certain and 2 hops, so the lexicographically
    # first path_key wins ("CON@a1..." < "CON@b1...").
    assert result.relationships[0].connection_type == "archimate-assignment"
    assert result.relationships[0].path_key == "CON@a1@fwd|CON@a2@fwd"


def test_reachability_respects_direction_hop_and_certainty_policies() -> None:
    graph = _Graph(
        {identifier: _entity(identifier) for identifier in ("A", "B", "C")},
        [
            _connection("CON@1", "A", "B", "archimate-specialization"),
            _connection("CON@2", "B", "C", "archimate-assignment"),
        ],
    )

    assert (
        derive_relationships(
            _request(frozenset({"A"}), hops=1, potential=True), read_access=graph, registries=_catalog()
        ).relationships
        == ()
    )
    assert (
        derive_relationships(
            _request(frozenset({"A"}), potential=False), read_access=graph, registries=_catalog()
        ).relationships
        == ()
    )
    outgoing = derive_relationships(
        _request(frozenset({"A"}), "outgoing", potential=True), read_access=graph, registries=_catalog()
    )
    incoming = derive_relationships(
        _request(frozenset({"C"}), "incoming", potential=True), read_access=graph, registries=_catalog()
    )

    assert outgoing.relationships[0].certainty == "potential"
    assert incoming.relationships[0].source_id == "A"


@dataclass
class _CountingGraph(_Graph):
    """Wraps `_Graph` to record how many times each entity's adjacency is actually
    fetched from the backing store — used to prove the BFS memoizes rather than
    re-fetching the same entity's connections every time it's revisited across
    different partial paths."""

    calls_by_entity: dict[str, int] = field(default_factory=dict)

    def find_connections_for(
        self, entity_id: str, *, direction: str = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        self.calls_by_entity[entity_id] = self.calls_by_entity.get(entity_id, 0) + 1
        return super().find_connections_for(entity_id, direction=direction, conn_type=conn_type)


def test_reachability_fetches_each_entitys_adjacency_at_most_once_even_when_revisited() -> None:
    # Diamond topology: D is reachable from A via two distinct 2-hop paths
    # (A-B-D and A-C-D), so a naive (non-memoized) BFS would fetch D's connections
    # once per path that reaches it; a properly memoized BFS fetches it once, period.
    graph = _CountingGraph(
        {identifier: _entity(identifier) for identifier in ("A", "B", "C", "D", "E")},
        [
            _connection("CON@ab", "A", "B", "archimate-assignment"),
            _connection("CON@ac", "A", "C", "archimate-assignment"),
            _connection("CON@bd", "B", "D", "archimate-assignment"),
            _connection("CON@cd", "C", "D", "archimate-assignment"),
            _connection("CON@de", "D", "E", "archimate-realization"),
        ],
    )

    derive_relationships(
        _request(frozenset({"A"}), "outgoing", hops=4), read_access=graph, registries=_catalog()
    )

    assert graph.calls_by_entity, "expected at least one adjacency fetch"
    over_fetched = {entity_id: count for entity_id, count in graph.calls_by_entity.items() if count > 1}
    assert not over_fetched, f"entities fetched more than once (memoization not engaging): {over_fetched}"


def test_reachability_never_traverses_dangling_connections_or_returns_partial_results() -> None:
    graph = _Graph(
        {identifier: _entity(identifier) for identifier in ("A", "B", "C", "D", "E")},
        [
            _connection("CON@dangling", "A", "missing", "archimate-assignment"),
            _connection("CON@1", "A", "B", "archimate-assignment"),
            _connection("CON@2", "B", "C", "archimate-realization"),
            _connection("CON@3", "A", "D", "archimate-assignment"),
            _connection("CON@4", "D", "E", "archimate-realization"),
        ],
    )

    with pytest.raises(DerivationLimitError):
        derive_relationships(_request(frozenset({"A"}), limit=1), read_access=graph, registries=_catalog())
