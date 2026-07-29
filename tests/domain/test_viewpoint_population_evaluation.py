"""Unit tests for population-level evaluation:
``NeighborInclusion`` widening and ``ConnectionSelection``/matrix-bridging connection
selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_population_evaluation import (
    resolve_neighbor_inclusions,
    select_connections,
    select_matrix_connections,
)
from tests.fixtures.viewpoints.derivation_examples import catalog, financial_application


def _entity(**kw: object) -> EntityRecord:
    defaults: dict[str, object] = dict(
        artifact_id="ENT@A",
        artifact_type="application-component",
        name="A",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="A",
        display_alias="",
    )
    defaults.update(kw)
    return EntityRecord(**defaults)  # type: ignore[arg-type]


def _connection(**kw: object) -> ConnectionRecord:
    defaults: dict[str, object] = dict(
        artifact_id="CON@001",
        source="ENT@A",
        target="ENT@B",
        conn_type="archimate-serving",
        version="1.0",
        status="draft",
        path=Path("/fake/conn.md"),
        extra={},
        content_text="",
    )
    defaults.update(kw)
    return ConnectionRecord(**defaults)  # type: ignore[arg-type]


@dataclass
class _Graph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return [c for c in self.connections if c.source == entity_id or c.target == entity_id]


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component", "process"}),
    known_connection_types=frozenset({"archimate-serving", "archimate-association"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={"strength": "integer"},
    symmetric_connection_types=frozenset({"archimate-association"}),
)


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


class TestNeighborInclusion:
    def _graph(self) -> _Graph:
        primary = _entity(artifact_id="ENT@primary", name="Primary")
        matching_neighbor = _entity(artifact_id="ENT@match", artifact_type="process", name="Match")
        non_matching_neighbor = _entity(artifact_id="ENT@nomatch", artifact_type="application-component", name="No")
        already_primary = _entity(artifact_id="ENT@also-primary", artifact_type="process", name="AlsoPrimary")
        return _Graph(
            entities={
                "ENT@primary": primary,
                "ENT@match": matching_neighbor,
                "ENT@nomatch": non_matching_neighbor,
                "ENT@also-primary": already_primary,
            },
            connections=[
                _connection(
                    artifact_id="CON@1", source="ENT@primary", target="ENT@match", conn_type="archimate-serving"
                ),
                _connection(
                    artifact_id="CON@2", source="ENT@primary", target="ENT@nomatch", conn_type="archimate-serving"
                ),
                _connection(
                    artifact_id="CON@3",
                    source="ENT@primary",
                    target="ENT@also-primary",
                    conn_type="archimate-serving",
                ),
            ],
        )

    def test_widens_population_with_matching_neighbor(self) -> None:
        graph = self._graph()
        inclusion = NeighborInclusion(neighbor_criteria=EntityCriteriaGroup(children=(_type_condition("process"),)))
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        assert "ENT@match" in result.expanded_ids
        assert "ENT@nomatch" not in result.expanded_ids

    def test_anchored_on_primary_only_no_chaining(self) -> None:
        primary = _entity(artifact_id="ENT@primary")
        neighbor = _entity(artifact_id="ENT@neighbor")
        two_hop = _entity(artifact_id="ENT@two-hop")
        graph = _Graph(
            entities={"ENT@primary": primary, "ENT@neighbor": neighbor, "ENT@two-hop": two_hop},
            connections=[
                _connection(
                    artifact_id="CON@1", source="ENT@primary", target="ENT@neighbor", conn_type="archimate-serving"
                ),
                _connection(
                    artifact_id="CON@2", source="ENT@neighbor", target="ENT@two-hop", conn_type="archimate-serving"
                ),
            ],
        )
        inclusion = NeighborInclusion()
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        # ENT@neighbor is reached from the primary anchor; ENT@two-hop is only reachable via
        # ENT@neighbor (a second hop) — inclusions never chain, so it must NOT appear.
        assert result.expanded_ids == frozenset({"ENT@neighbor"})

    def test_membership_precedence_primary_wins(self) -> None:
        graph = self._graph()
        inclusion = NeighborInclusion()
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary", "ENT@also-primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        # already-primary entity is never re-added as expanded
        assert "ENT@also-primary" not in result.expanded_ids

    def test_dedup_across_two_inclusion_terms(self) -> None:
        graph = self._graph()
        term_a = NeighborInclusion(neighbor_criteria=EntityCriteriaGroup(children=(_type_condition("process"),)))
        term_b = NeighborInclusion()  # matches everything, including ENT@match again
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (term_a, term_b), read_access=graph, registries=_REGISTRIES
        )
        # ENT@match is matched by both terms — appears exactly once (set semantics prove it).
        assert result.expanded_ids == frozenset({"ENT@match", "ENT@nomatch", "ENT@also-primary"})

    def test_anchor_relative_direction(self) -> None:
        graph = self._graph()
        inclusion = NeighborInclusion(direction="incoming")  # anchor has no incoming connections
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        assert result.expanded_ids == frozenset()

    def test_dangling_neighbor_never_included(self) -> None:
        graph = self._graph()
        graph.connections.append(
            _connection(
                artifact_id="CON@dangling", source="ENT@primary", target="ENT@ghost", conn_type="archimate-serving"
            )
        )
        inclusion = NeighborInclusion()
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        assert "ENT@ghost" not in result.expanded_ids

    def test_schema_drift_from_neighbor_criteria_bubbles_up(self) -> None:
        graph = self._graph()
        inclusion = NeighborInclusion(
            neighbor_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="legacy_field", comparator="exists"),)
            )
        )
        result = resolve_neighbor_inclusions(
            frozenset({"ENT@primary"}), (inclusion,), read_access=graph, registries=_REGISTRIES
        )
        assert result.schema_drift == frozenset({"legacy_field"})


class TestConnectionSelection:
    def _graph(self) -> _Graph:
        entity_a = _entity(artifact_id="ENT@A")
        entity_b = _entity(artifact_id="ENT@B")
        entity_c = _entity(artifact_id="ENT@C")  # outside the included set
        return _Graph(
            entities={"ENT@A": entity_a, "ENT@B": entity_b, "ENT@C": entity_c},
            connections=[
                _connection(artifact_id="CON@ab", source="ENT@A", target="ENT@B", conn_type="archimate-serving"),
                _connection(artifact_id="CON@ac", source="ENT@A", target="ENT@C", conn_type="archimate-serving"),
            ],
        )

    def test_structural_invariant_both_endpoints_must_be_included(self) -> None:
        graph = self._graph()
        result = select_connections(
            frozenset({"ENT@A", "ENT@B"}), ConnectionSelection(), read_access=graph, registries=_REGISTRIES
        )
        ids = {c.artifact_id for c in result.connections}
        assert ids == {"CON@ab"}

    def test_disabled_selection_returns_nothing(self) -> None:
        graph = self._graph()
        result = select_connections(
            frozenset({"ENT@A", "ENT@B"}), ConnectionSelection(enabled=False), read_access=graph, registries=_REGISTRIES
        )
        assert result.connections == ()

    def test_criteria_narrows_but_cannot_widen(self) -> None:
        graph = self._graph()
        selection = ConnectionSelection(
            criteria=ConnectionCriteriaGroup(
                children=(AttributeCondition(attribute="id", comparator="eq", value=ValueRef(literal="CON@ac")),)
            )
        )
        # CON@ac is structurally excluded (ENT@C not in the included set) even though the
        # criteria alone would match it.
        result = select_connections(frozenset({"ENT@A", "ENT@B"}), selection, read_access=graph, registries=_REGISTRIES)
        assert result.connections == ()

    def test_deterministic_ordering_by_artifact_id(self) -> None:
        graph = self._graph()
        graph.connections.append(
            _connection(artifact_id="CON@aa", source="ENT@A", target="ENT@B", conn_type="archimate-association")
        )
        result = select_connections(
            frozenset({"ENT@A", "ENT@B"}), ConnectionSelection(), read_access=graph, registries=_REGISTRIES
        )
        ids = [c.artifact_id for c in result.connections]
        assert ids == sorted(ids)


class TestMatrixBridging:
    def _graph(self) -> _Graph:
        row_entity = _entity(artifact_id="ENT@row")
        column_entity = _entity(artifact_id="ENT@col")
        other_row_entity = _entity(artifact_id="ENT@row2")
        return _Graph(
            entities={"ENT@row": row_entity, "ENT@col": column_entity, "ENT@row2": other_row_entity},
            connections=[
                _connection(
                    artifact_id="CON@bridge", source="ENT@row", target="ENT@col", conn_type="archimate-serving"
                ),
                _connection(
                    artifact_id="CON@within-row", source="ENT@row", target="ENT@row2", conn_type="archimate-serving"
                ),
            ],
        )

    def test_bridging_invariant_row_to_column_only(self) -> None:
        graph = self._graph()
        result = select_matrix_connections(
            frozenset({"ENT@row", "ENT@row2"}),
            frozenset({"ENT@col"}),
            ConnectionSelection(),
            read_access=graph,
            registries=_REGISTRIES,
        )
        ids = {c.artifact_id for c in result.connections}
        # the row<->row connection must be excluded — bridging is row<->column only.
        assert ids == {"CON@bridge"}

    def test_disjoint_populations_produce_correct_set(self) -> None:
        graph = self._graph()
        result = select_matrix_connections(
            frozenset({"ENT@row2"}),
            frozenset({"ENT@col"}),
            ConnectionSelection(),
            read_access=graph,
            registries=_REGISTRIES,
        )
        assert result.connections == ()

    def test_disabled_selection_on_matrix_returns_nothing(self) -> None:
        graph = self._graph()
        result = select_matrix_connections(
            frozenset({"ENT@row"}),
            frozenset({"ENT@col"}),
            ConnectionSelection(enabled=False),
            read_access=graph,
            registries=_REGISTRIES,
        )
        assert result.connections == ()


class TestDerivedConnectionSelection:
    def test_derived_connection_respects_structural_endpoints(self) -> None:
        graph = financial_application()
        relationship_catalog = catalog()
        registries = RegistrySnapshot(
            frozenset(relationship_catalog.all_entity_types()),
            frozenset(relationship_catalog.all_connection_types()),
            frozenset(),
            {},
            {},
            derivation_catalog=relationship_catalog,
        )
        selection = ConnectionSelection(
            traversal="derived",
            max_hops=3,
            criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-realization"),)),
        )
        result = select_connections(
            frozenset({"financial-application", "payment-service"}),
            selection,
            read_access=graph,
            registries=registries,
        )
        assert result.connections == ()
        assert [(item.source_id, item.target_id, item.connection_type) for item in result.derived_connections] == [
            ("financial-application", "payment-service", "archimate-realization")
        ]

    def test_derived_connection_obeys_matrix_bridging(self) -> None:
        graph = financial_application()
        relationship_catalog = catalog()
        registries = RegistrySnapshot(
            frozenset(relationship_catalog.all_entity_types()),
            frozenset(relationship_catalog.all_connection_types()),
            frozenset(),
            {},
            {},
            derivation_catalog=relationship_catalog,
        )
        result = select_matrix_connections(
            frozenset({"financial-application"}),
            frozenset({"payment-service"}),
            ConnectionSelection(traversal="derived", max_hops=3),
            read_access=graph,
            registries=registries,
        )
        assert [(item.source_id, item.target_id) for item in result.derived_connections] == [
            ("financial-application", "payment-service")
        ]
