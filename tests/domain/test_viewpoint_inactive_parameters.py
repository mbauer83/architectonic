"""Unset OPTIONAL parameters drop their condition out of the conjunction instead of failing
to match — the semantic that makes an optional filter (e.g. `group`) expressible at all.

Pins the subtleties: an UNKNOWN parameter name must still fail (dropping would silently widen),
inactivity propagates when every child of a group is inactive, a negated inactive group stays
inactive, and an inactive term never rescues a failing sibling under `or`.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_criteria_evaluation import evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationEnvironment

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"goal"}), known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(), entity_attribute_types={}, connection_attribute_types={},
)


class _NoReadAccess:
    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return None

    def get_connection(self, artifact_id: str):
        return None

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return []


def _entity(group: str = "platform-core") -> EntityRecord:
    return EntityRecord(
        artifact_id="GOL@1", artifact_type="goal", name="G", version="1.0", status="active",
        domain="motivation", subdomain="goal", path=Path("/fake.md"), keywords=(), extra={},
        content_text="", display_blocks={}, display_label="G", display_alias="", group=group,
    )


def _param_condition(name: str, attribute: str = "group") -> AttributeCondition:
    return AttributeCondition(attribute, "eq", ValueRef(kind="parameter", parameter=name))


def _type_condition() -> AttributeCondition:
    return AttributeCondition("type", "eq", ValueRef(literal="goal"))


def _evaluate(group: EntityCriteriaGroup, *, inactive: frozenset[str] = frozenset(), entity=None):
    return evaluate_entity_criteria(
        group, entity or _entity(), read_access=_NoReadAccess(), registries=_REGISTRIES,
        environment=EvaluationEnvironment(inactive_parameters=inactive),
    )


class TestUnsetOptionalDrops:
    def test_unset_optional_condition_does_not_exclude(self) -> None:
        criteria = EntityCriteriaGroup(children=(_type_condition(), _param_condition("group")))
        assert _evaluate(criteria, inactive=frozenset({"group"})).matched is True

    def test_sole_unset_condition_makes_the_root_match_everything(self) -> None:
        criteria = EntityCriteriaGroup(children=(_param_condition("group"),))
        assert _evaluate(criteria, inactive=frozenset({"group"})).matched is True

    def test_a_failing_sibling_still_decides(self) -> None:
        failing = AttributeCondition("type", "eq", ValueRef(literal="outcome"))
        criteria = EntityCriteriaGroup(children=(failing, _param_condition("group")))
        assert _evaluate(criteria, inactive=frozenset({"group"})).matched is False


class TestUnknownParameterStillFails:
    def test_unknown_parameter_name_does_not_drop(self) -> None:
        # A typo must NOT silently remove the filter — dropping widens results, which is the
        # dangerous direction; only DECLARED optional parameters are ever inactive.
        criteria = EntityCriteriaGroup(children=(_param_condition("typoed"),))
        assert _evaluate(criteria, inactive=frozenset({"group"})).matched is False


class TestPropagation:
    def test_group_with_all_children_inactive_is_itself_inactive(self) -> None:
        inner = EntityCriteriaGroup(conjunction="or", children=(_param_condition("a"), _param_condition("b")))
        outer = EntityCriteriaGroup(children=(_type_condition(), inner))
        # Without propagation the empty `or` would collapse to no-match and sink the outer `and`.
        assert _evaluate(outer, inactive=frozenset({"a", "b"})).matched is True

    def test_inner_or_with_one_active_failing_child_still_fails(self) -> None:
        failing = AttributeCondition("type", "eq", ValueRef(literal="outcome"))
        inner = EntityCriteriaGroup(conjunction="or", children=(failing, _param_condition("a")))
        outer = EntityCriteriaGroup(children=(_type_condition(), inner))
        assert _evaluate(outer, inactive=frozenset({"a"})).matched is False

    def test_negated_inactive_group_stays_inactive(self) -> None:
        # "NOT (nothing asserted)" asserts nothing either — negating it would invent a filter.
        inner = EntityCriteriaGroup(children=(_param_condition("a"),), negate=True)
        outer = EntityCriteriaGroup(children=(_type_condition(), inner))
        assert _evaluate(outer, inactive=frozenset({"a"})).matched is True


class TestActiveParameterStillFilters:
    def test_supplied_parameter_filters_normally(self) -> None:
        criteria = EntityCriteriaGroup(children=(_param_condition("group"),))
        outcome = evaluate_entity_criteria(
            criteria, _entity(group="other"), read_access=_NoReadAccess(), registries=_REGISTRIES,
            environment=EvaluationEnvironment(parameters={"group": "platform-core"}),
        )
        assert outcome.matched is False
