"""Unit tests for tree-recursive criteria evaluation: group
conjunction/negate semantics, empty-group behavior, and ``IncidentConnectionCondition``
(direction, connection/endpoint narrowing, recursion, negate, dangling endpoints, symmetric
normalization). Leaf comparator semantics live in ``test_viewpoint_condition_evaluation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_criteria_evaluation import (
    direction_matches,
    evaluate_entity_criteria,
)


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
    entity_attribute_types={"threshold": "integer"},
    connection_attribute_types={"strength": "integer"},
    symmetric_connection_types=frozenset({"archimate-association"}),
)


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


class TestGroupSemantics:
    def test_and_requires_all_children(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        group = EntityCriteriaGroup(
            conjunction="and",
            children=(
                _type_condition("application-component"),
                AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="draft")),
            ),
        )
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is True

    def test_and_fails_if_one_child_fails(self) -> None:
        entity = _entity(status="approved")
        group = EntityCriteriaGroup(
            conjunction="and",
            children=(
                _type_condition("application-component"),
                AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="draft")),
            ),
        )
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is False

    def test_or_matches_if_any_child_matches(self) -> None:
        entity = _entity(status="approved")
        group = EntityCriteriaGroup(
            conjunction="or",
            children=(
                AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="draft")),
                AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="approved")),
            ),
        )
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is True

    def test_empty_root_group_matches_all(self) -> None:
        entity = _entity()
        outcome = evaluate_entity_criteria(EntityCriteriaGroup(), entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is True

    def test_empty_or_group_matches_nothing(self) -> None:
        entity = _entity()
        group = EntityCriteriaGroup(conjunction="or", children=())
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is False

    def test_group_negate_complements_result(self) -> None:
        entity = _entity()
        group = EntityCriteriaGroup(children=(), negate=True)  # empty AND = True, negated = False
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is False

    def test_nested_group_recurses(self) -> None:
        entity = _entity(status="draft")
        inner = EntityCriteriaGroup(
            conjunction="or",
            children=(AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="draft")),),
        )
        outer = EntityCriteriaGroup(conjunction="and", children=(_type_condition("application-component"), inner))
        outcome = evaluate_entity_criteria(outer, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.matched is True

    def test_schema_drift_bubbles_up_through_group(self) -> None:
        entity = _entity(extra={"legacy": 1})
        group = EntityCriteriaGroup(
            children=(AttributeCondition(attribute="legacy", comparator="exists"),),
        )
        outcome = evaluate_entity_criteria(group, entity, read_access=_Graph(), registries=_REGISTRIES)
        assert outcome.schema_drift == frozenset({"legacy"})


class TestDirectionMatches:
    def test_either_always_passes(self) -> None:
        connection = _connection(conn_type="archimate-serving")
        assert direction_matches(connection, "ENT@A", "either", _REGISTRIES) is True

    def test_directed_type_honors_requested_direction(self) -> None:
        connection = _connection(source="ENT@A", target="ENT@B", conn_type="archimate-serving")
        assert direction_matches(connection, "ENT@A", "outgoing", _REGISTRIES) is True
        assert direction_matches(connection, "ENT@A", "incoming", _REGISTRIES) is False
        assert direction_matches(connection, "ENT@B", "incoming", _REGISTRIES) is True

    def test_symmetric_type_ignores_requested_direction(self) -> None:
        connection = _connection(source="ENT@C", target="ENT@A", conn_type="archimate-association")
        assert direction_matches(connection, "ENT@A", "outgoing", _REGISTRIES) is True
        assert direction_matches(connection, "ENT@A", "incoming", _REGISTRIES) is True


def _matches_a(condition: IncidentConnectionCondition, graph: _Graph) -> bool:
    outcome = evaluate_entity_criteria(
        EntityCriteriaGroup(children=(condition,)), graph.entities["ENT@A"], read_access=graph, registries=_REGISTRIES
    )
    return outcome.matched


class TestIncidentConnectionCondition:
    def _graph(self) -> _Graph:
        entity_a = _entity(artifact_id="ENT@A", extra={"threshold": 3})
        entity_b = _entity(artifact_id="ENT@B", artifact_type="process", name="B")
        entity_c = _entity(artifact_id="ENT@C", artifact_type="process", name="C")
        directed = _connection(
            artifact_id="CON@directed",
            source="ENT@A",
            target="ENT@B",
            conn_type="archimate-serving",
            extra={"strength": 5},
        )
        symmetric = _connection(
            artifact_id="CON@symmetric", source="ENT@C", target="ENT@A", conn_type="archimate-association"
        )
        dangling = _connection(
            artifact_id="CON@dangling", source="ENT@A", target="ENT@ghost", conn_type="archimate-serving"
        )
        return _Graph(
            entities={"ENT@A": entity_a, "ENT@B": entity_b, "ENT@C": entity_c},
            connections=[directed, symmetric, dangling],
        )

    def test_matches_when_connection_and_endpoint_criteria_satisfied(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            direction="outgoing",
            endpoint_criteria=EntityCriteriaGroup(children=(_type_condition("process"),)),
        )
        assert _matches_a(condition, self._graph()) is True

    def test_direction_outgoing_rejects_incoming_connection(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            direction="incoming",
        )
        assert _matches_a(condition, self._graph()) is False

    def test_symmetric_connection_matches_regardless_of_direction(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-association"),)),
            direction="outgoing",
        )
        assert _matches_a(condition, self._graph()) is True

    def test_value_ref_inside_connection_criteria_resolves_against_traversed_connection(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="strength",
                        comparator="gt",
                        value=ValueRef(kind="attribute_of_endpoint", endpoint="source", attribute="threshold"),
                    ),
                )
            ),
        )
        assert _matches_a(condition, self._graph()) is True  # strength=5 > A.threshold=3

    def test_dangling_endpoint_never_matches(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(
                children=(AttributeCondition(attribute="id", comparator="eq", value=ValueRef(literal="CON@dangling")),)
            ),
        )
        assert _matches_a(condition, self._graph()) is False

    def test_negate_means_has_no_such_connection(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            negate=True,
        )
        # A DOES have such a connection, negated -> no match
        assert _matches_a(condition, self._graph()) is False

    def test_negate_matches_when_no_incident_connection_satisfies(self) -> None:
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-realization"),)),
            negate=True,
        )
        assert _matches_a(condition, self._graph()) is True

    def test_recursive_endpoint_criteria_two_hops(self) -> None:
        graph = self._graph()
        # B --serving--> C, both entities already present in the graph
        graph.connections.append(
            _connection(artifact_id="CON@bc", source="ENT@B", target="ENT@C", conn_type="archimate-serving")
        )
        inner_endpoint = EntityCriteriaGroup(
            children=(AttributeCondition(attribute="id", comparator="eq", value=ValueRef(literal="ENT@C")),)
        )
        condition = IncidentConnectionCondition(
            connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
            direction="outgoing",
            endpoint_criteria=EntityCriteriaGroup(
                children=(
                    IncidentConnectionCondition(
                        connection_criteria=ConnectionCriteriaGroup(children=(_type_condition("archimate-serving"),)),
                        direction="outgoing",
                        endpoint_criteria=inner_endpoint,
                    ),
                )
            ),
        )
        assert _matches_a(condition, graph) is True
