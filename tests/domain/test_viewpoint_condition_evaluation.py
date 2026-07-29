"""Unit tests for leaf ``AttributeCondition`` evaluation: the
per-comparator × presence semantics table, ``negate`` complement, ``ValueRef`` resolution,
no-coercion behavior, and schema-drift detection. Group/tree recursion and ``IncidentConnectionCondition`` live in
``test_viewpoint_criteria_evaluation.py``; population widening/connection selection in
``test_viewpoint_population_evaluation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_evaluation import evaluate_attribute_condition
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, ValueRef
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationOutcome


def _entity(**kw: object) -> EntityRecord:
    defaults: dict[str, object] = dict(
        artifact_id="ENT@001",
        artifact_type="application-component",
        name="My Service",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="My Service",
        display_alias="",
    )
    defaults.update(kw)
    return EntityRecord(**defaults)  # type: ignore[arg-type]


def _connection(**kw: object) -> ConnectionRecord:
    defaults: dict[str, object] = dict(
        artifact_id="CON@001",
        source="ENT@001",
        target="ENT@002",
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
class _FakeReadAccess:
    entities: dict[str, EntityRecord] = field(default_factory=dict)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return []


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component"}),
    known_connection_types=frozenset({"archimate-serving"}),
    known_specialization_slugs=frozenset({"business-process"}),
    entity_attribute_types={"risk_score": "integer", "owner": "string", "start_date": "date"},
    connection_attribute_types={"strength": "integer"},
)


def _condition(attribute: str, comparator: str, literal: object = None, negate: bool = False) -> AttributeCondition:
    return AttributeCondition(
        attribute=attribute, comparator=comparator, value=ValueRef(literal=literal), negate=negate
    )


def _eval_entity(condition: AttributeCondition, entity: EntityRecord) -> EvaluationOutcome:
    return evaluate_attribute_condition(
        condition,
        record=entity,
        context="entity",
        read_access=_FakeReadAccess(),
        registries=_REGISTRIES,
        connection=None,
    )


class TestComparatorPresenceTable:
    def test_eq_missing_no_match(self) -> None:
        entity = _entity(extra={})
        assert _eval_entity(_condition("risk_score", "eq", 5), entity).matched is False

    def test_eq_present_scalar(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        assert _eval_entity(_condition("risk_score", "eq", 5), entity).matched is True
        assert _eval_entity(_condition("risk_score", "eq", 6), entity).matched is False

    def test_eq_present_multivalued_any_element(self) -> None:
        entity = _entity(extra={"risk_score": [1, 5, 9]})
        assert _eval_entity(_condition("risk_score", "eq", 5), entity).matched is True
        assert _eval_entity(_condition("risk_score", "eq", 2), entity).matched is False

    def test_neq_missing_is_no_match_not_trivially_unequal(self) -> None:
        entity = _entity(extra={})
        assert _eval_entity(_condition("risk_score", "neq", 5), entity).matched is False

    def test_neq_present_scalar(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        assert _eval_entity(_condition("risk_score", "neq", 6), entity).matched is True
        assert _eval_entity(_condition("risk_score", "neq", 5), entity).matched is False

    def test_neq_present_multivalued_requires_no_element_equal(self) -> None:
        entity = _entity(extra={"risk_score": [1, 5, 9]})
        assert _eval_entity(_condition("risk_score", "neq", 5), entity).matched is False
        assert _eval_entity(_condition("risk_score", "neq", 2), entity).matched is True

    def test_in_missing_no_match(self) -> None:
        entity = _entity(extra={})
        assert _eval_entity(_condition("risk_score", "in", [1, 2, 3]), entity).matched is False

    def test_in_present_scalar(self) -> None:
        entity = _entity(extra={"risk_score": 2})
        assert _eval_entity(_condition("risk_score", "in", [1, 2, 3]), entity).matched is True
        assert _eval_entity(_condition("risk_score", "in", [9]), entity).matched is False

    def test_in_present_multivalued_any_element(self) -> None:
        entity = _entity(extra={"risk_score": [7, 8]})
        assert _eval_entity(_condition("risk_score", "in", [1, 8]), entity).matched is True
        assert _eval_entity(_condition("risk_score", "in", [1, 2]), entity).matched is False

    def test_exists_missing_no_match(self) -> None:
        entity = _entity(extra={})
        condition = AttributeCondition(attribute="risk_score", comparator="exists")
        assert _eval_entity(condition, entity).matched is False

    def test_exists_present_matches_scalar_and_multivalued(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="exists")
        assert _eval_entity(condition, _entity(extra={"risk_score": 5})).matched is True
        assert _eval_entity(condition, _entity(extra={"risk_score": [1, 2]})).matched is True

    def test_absent_missing_matches(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="absent")
        assert _eval_entity(condition, _entity(extra={})).matched is True

    def test_absent_present_no_match(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="absent")
        assert _eval_entity(condition, _entity(extra={"risk_score": 5})).matched is False
        assert _eval_entity(condition, _entity(extra={"risk_score": [1]})).matched is False

    @pytest.mark.parametrize("comparator", ["lt", "lte", "gt", "gte"])
    def test_numeric_missing_no_match(self, comparator: str) -> None:
        condition = _condition("risk_score", comparator, 5)
        assert _eval_entity(condition, _entity(extra={})).matched is False

    def test_numeric_present_scalar_typed_compare(self) -> None:
        entity = _entity(extra={"risk_score": 3})
        assert _eval_entity(_condition("risk_score", "lt", 5), entity).matched is True
        assert _eval_entity(_condition("risk_score", "gt", 5), entity).matched is False

    def test_numeric_present_multivalued_any_element_satisfies(self) -> None:
        entity = _entity(extra={"risk_score": [1, 9]})
        assert _eval_entity(_condition("risk_score", "gt", 5), entity).matched is True
        assert _eval_entity(_condition("risk_score", "gt", 20), entity).matched is False


class TestNegateComplement:
    def test_negate_flips_ordinary_match(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        assert _eval_entity(_condition("risk_score", "eq", 5, negate=True), entity).matched is False
        assert _eval_entity(_condition("risk_score", "eq", 6, negate=True), entity).matched is True

    def test_eq_negate_on_missing_attribute_matches(self) -> None:
        """Strict logical complement: 'is not X' on an unset attribute counts as satisfied —
        excluding everything marked X should include everything unmarked."""
        entity = _entity(extra={})
        assert _eval_entity(_condition("risk_score", "eq", 5, negate=True), entity).matched is True

    def test_absent_negate_is_exists(self) -> None:
        condition = AttributeCondition(attribute="risk_score", comparator="absent", negate=True)
        assert _eval_entity(condition, _entity(extra={"risk_score": 5})).matched is True
        assert _eval_entity(condition, _entity(extra={})).matched is False


class TestNoCoercion:
    def test_numeric_comparator_on_incompatible_value_is_no_match_not_a_crash(self) -> None:
        entity = _entity(extra={"risk_score": "not-a-number"})
        outcome = _eval_entity(_condition("risk_score", "lt", 5), entity)
        assert outcome.matched is False

    def test_dates_compare_as_iso_strings(self) -> None:
        entity = _entity(extra={"start_date": "2026-01-01"})
        assert _eval_entity(_condition("start_date", "lt", "2026-06-01"), entity).matched is True
        assert _eval_entity(_condition("start_date", "gt", "2026-06-01"), entity).matched is False


class TestReservedPaths:
    def test_id_name_type_domain_subdomain_status_version_readable(self) -> None:
        entity = _entity(
            artifact_id="ENT@42",
            name="Checkout",
            artifact_type="application-component",
            domain="application",
            subdomain="app-service",
            status="approved",
            version="2.0",
        )
        for path, expected in (
            ("id", "ENT@42"),
            ("name", "Checkout"),
            ("type", "application-component"),
            ("domain", "application"),
            ("subdomain", "app-service"),
            ("status", "approved"),
            ("version", "2.0"),
        ):
            assert _eval_entity(_condition(path, "eq", expected), entity).matched is True

    def test_specialization_empty_string_is_absent(self) -> None:
        entity = _entity(specialization="")
        absent = AttributeCondition(attribute="specialization", comparator="absent")
        exists = AttributeCondition(attribute="specialization", comparator="exists")
        assert _eval_entity(absent, entity).matched is True
        assert _eval_entity(exists, entity).matched is False

    def test_specialization_present_when_set(self) -> None:
        entity = _entity(specialization="business-process")
        assert _eval_entity(AttributeCondition(attribute="specialization", comparator="exists"), entity).matched is True

    def test_connection_reserved_type_readable(self) -> None:
        connection = _connection(conn_type="archimate-serving")
        condition = _condition("type", "eq", "archimate-serving")
        outcome = evaluate_attribute_condition(
            condition,
            record=connection,
            context="connection",
            read_access=_FakeReadAccess(),
            registries=_REGISTRIES,
            connection=connection,
        )
        assert outcome.matched is True


class TestValueRefResolution:
    def test_attribute_of_self_compares_two_attributes_on_same_record(self) -> None:
        entity = _entity(extra={"start_date": "2026-01-01", "end_date": "2026-06-01"})
        condition = AttributeCondition(
            attribute="start_date",
            comparator="lt",
            value=ValueRef(kind="attribute_of_self", attribute="end_date"),
        )
        registries = RegistrySnapshot(
            known_entity_types=frozenset({"application-component"}),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"start_date": "date", "end_date": "date"},
            connection_attribute_types={},
        )
        outcome = evaluate_attribute_condition(
            condition,
            record=entity,
            context="entity",
            read_access=_FakeReadAccess(),
            registries=registries,
            connection=None,
        )
        assert outcome.matched is True

    def test_attribute_of_self_unresolvable_reference_is_no_match(self) -> None:
        entity = _entity(extra={"start_date": "2026-01-01"})
        condition = AttributeCondition(
            attribute="start_date",
            comparator="lt",
            value=ValueRef(kind="attribute_of_self", attribute="end_date"),
        )
        registries = RegistrySnapshot(
            known_entity_types=frozenset(),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"start_date": "date", "end_date": "date"},
            connection_attribute_types={},
        )
        outcome = evaluate_attribute_condition(
            condition,
            record=entity,
            context="entity",
            read_access=_FakeReadAccess(),
            registries=registries,
            connection=None,
        )
        assert outcome.matched is False

    def test_attribute_of_endpoint_reads_source_entity_attribute(self) -> None:
        source = _entity(artifact_id="ENT@src", extra={"threshold": 3})
        connection = _connection(source="ENT@src", target="ENT@tgt", extra={"strength": 5})
        condition = AttributeCondition(
            attribute="strength",
            comparator="gt",
            value=ValueRef(kind="attribute_of_endpoint", endpoint="source", attribute="threshold"),
        )
        registries = RegistrySnapshot(
            known_entity_types=frozenset(),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"threshold": "integer"},
            connection_attribute_types={"strength": "integer"},
        )
        read_access = _FakeReadAccess(entities={"ENT@src": source})
        outcome = evaluate_attribute_condition(
            condition,
            record=connection,
            context="connection",
            read_access=read_access,
            registries=registries,
            connection=connection,
        )
        assert outcome.matched is True

    def test_attribute_of_endpoint_reads_target_entity_attribute(self) -> None:
        target = _entity(artifact_id="ENT@tgt", extra={"threshold": 10})
        connection = _connection(source="ENT@src", target="ENT@tgt", extra={"strength": 5})
        condition = AttributeCondition(
            attribute="strength",
            comparator="gt",
            value=ValueRef(kind="attribute_of_endpoint", endpoint="target", attribute="threshold"),
        )
        registries = RegistrySnapshot(
            known_entity_types=frozenset(),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"threshold": "integer"},
            connection_attribute_types={"strength": "integer"},
        )
        read_access = _FakeReadAccess(entities={"ENT@tgt": target})
        outcome = evaluate_attribute_condition(
            condition,
            record=connection,
            context="connection",
            read_access=read_access,
            registries=registries,
            connection=connection,
        )
        assert outcome.matched is False  # 5 > 10 is false

    def test_attribute_of_endpoint_unresolvable_entity_is_no_match(self) -> None:
        connection = _connection(source="ENT@ghost", target="ENT@tgt", extra={"strength": 5})
        condition = AttributeCondition(
            attribute="strength",
            comparator="gt",
            value=ValueRef(kind="attribute_of_endpoint", endpoint="source", attribute="threshold"),
        )
        registries = RegistrySnapshot(
            known_entity_types=frozenset(),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"threshold": "integer"},
            connection_attribute_types={"strength": "integer"},
        )
        outcome = evaluate_attribute_condition(
            condition,
            record=connection,
            context="connection",
            read_access=_FakeReadAccess(),
            registries=registries,
            connection=connection,
        )
        assert outcome.matched is False

    def test_attribute_of_endpoint_outside_connection_context_is_no_match(self) -> None:
        entity = _entity(extra={"strength": 5})
        condition = AttributeCondition(
            attribute="strength",
            comparator="gt",
            value=ValueRef(kind="attribute_of_endpoint", endpoint="source", attribute="threshold"),
        )
        outcome = evaluate_attribute_condition(
            condition,
            record=entity,
            context="entity",
            read_access=_FakeReadAccess(),
            registries=_REGISTRIES,
            connection=None,
        )
        assert outcome.matched is False


class TestSchemaDrift:
    def test_attribute_unknown_at_evaluation_time_is_no_match_and_warns(self) -> None:
        entity = _entity(extra={"legacy_field": 5})
        condition = _condition("legacy_field", "eq", 5)
        outcome = _eval_entity(condition, entity)
        assert outcome.matched is False
        assert outcome.schema_drift == frozenset({"legacy_field"})

    def test_known_attribute_produces_no_drift_warning(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        outcome = _eval_entity(_condition("risk_score", "eq", 5), entity)
        assert outcome.schema_drift == frozenset()

    def test_drifted_value_ref_reference_also_warns(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        condition = AttributeCondition(
            attribute="risk_score", comparator="eq", value=ValueRef(kind="attribute_of_self", attribute="ghost_field")
        )
        outcome = _eval_entity(condition, entity)
        assert outcome.matched is False
        assert outcome.schema_drift == frozenset({"ghost_field"})
