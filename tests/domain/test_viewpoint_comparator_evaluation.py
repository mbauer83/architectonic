"""Evaluation semantics for the expressive comparators (`not_in`, `like`, `ilike`):
case/escaping behavior for patterns, the presence table (missing/scalar/multi-valued),
negate interaction, and every operand kind (literal, parameter, binding,
attribute reference)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_evaluation import evaluate_attribute_condition
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, ValueRef
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationEnvironment


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


class _FakeReadAccess:
    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return None

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return []


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"owner": "string", "risk_score": "integer", "owner_pattern": "string"},
    connection_attribute_types={},
)


def _condition(attribute: str, comparator: str, value: object, *, negate: bool = False) -> AttributeCondition:
    return AttributeCondition(attribute=attribute, comparator=comparator, value=ValueRef(literal=value), negate=negate)


def _eval(condition: AttributeCondition, entity: EntityRecord, *, environment: EvaluationEnvironment | None = None):
    return evaluate_attribute_condition(
        condition,
        record=entity,
        context="entity",
        read_access=_FakeReadAccess(),
        registries=_REGISTRIES,
        connection=None,
        environment=environment or EvaluationEnvironment(),
    )


class TestNotIn:
    def test_missing_attribute_no_match(self) -> None:
        assert _eval(_condition("owner", "not_in", ["a", "b"]), _entity(extra={})).matched is False

    def test_present_scalar_not_member(self) -> None:
        entity = _entity(extra={"owner": "carol"})
        assert _eval(_condition("owner", "not_in", ["a", "b"]), entity).matched is True

    def test_present_scalar_member(self) -> None:
        entity = _entity(extra={"owner": "a"})
        assert _eval(_condition("owner", "not_in", ["a", "b"]), entity).matched is False

    def test_present_multivalued_requires_no_element_member(self) -> None:
        entity = _entity(extra={"owner": ["c", "d"]})
        assert _eval(_condition("owner", "not_in", ["a", "b"]), entity).matched is True
        assert _eval(_condition("owner", "not_in", ["a", "d"]), entity).matched is False

    def test_negate_is_strict_complement(self) -> None:
        entity = _entity(extra={"owner": "a"})
        assert _eval(_condition("owner", "not_in", ["a", "b"], negate=True), entity).matched is True
        # Strict complement: missing attribute is "no match" before negate, so negate flips
        # it to a match — mirroring eq+negate's "excluding X should include unmarked items".
        missing = _entity(extra={})
        assert _eval(_condition("owner", "not_in", ["a", "b"], negate=True), missing).matched is True


class TestLikeCaseSensitive:
    def test_missing_attribute_no_match(self) -> None:
        assert _eval(_condition("owner", "like", "car%"), _entity(extra={})).matched is False

    @pytest.mark.parametrize(
        ("pattern", "text", "expected"),
        [
            ("car%", "carol", True),
            ("car%", "Carol", False),
            ("%ol", "carol", True),
            ("c_rol", "carol", True),
            ("c_rol", "carrol", False),
            ("carol", "carol", True),
            ("carol", "carolina", False),
        ],
    )
    def test_wildcards_and_case(self, pattern: str, text: str, expected: bool) -> None:
        entity = _entity(extra={"owner": text})
        assert _eval(_condition("owner", "like", pattern), entity).matched is expected

    def test_backslash_escapes_percent_literally(self) -> None:
        entity = _entity(extra={"owner": "50%"})
        assert _eval(_condition("owner", "like", r"50\%"), entity).matched is True
        assert _eval(_condition("owner", "like", r"50\%"), _entity(extra={"owner": "50x"})).matched is False

    def test_backslash_escapes_underscore_literally(self) -> None:
        entity = _entity(extra={"owner": "a_b"})
        assert _eval(_condition("owner", "like", r"a\_b"), entity).matched is True
        assert _eval(_condition("owner", "like", r"a\_b"), _entity(extra={"owner": "axb"})).matched is False

    def test_trailing_lone_backslash_is_literal_not_a_crash(self) -> None:
        entity = _entity(extra={"owner": "carol\\"})
        outcome = _eval(_condition("owner", "like", "carol\\"), entity)
        assert outcome.matched is True

    def test_present_multivalued_any_element_matches(self) -> None:
        entity = _entity(extra={"owner": ["dave", "carol"]})
        assert _eval(_condition("owner", "like", "car%"), entity).matched is True
        assert _eval(_condition("owner", "like", "zzz%"), entity).matched is False

    def test_non_string_actual_is_no_match_not_a_crash(self) -> None:
        entity = _entity(extra={"risk_score": 5})
        assert _eval(_condition("risk_score", "like", "5"), entity).matched is False

    def test_negate_is_strict_complement(self) -> None:
        entity = _entity(extra={"owner": "carol"})
        assert _eval(_condition("owner", "like", "car%", negate=True), entity).matched is False
        assert _eval(_condition("owner", "like", "zzz%", negate=True), entity).matched is True


class TestIlikeCaseInsensitive:
    def test_case_insensitive_match(self) -> None:
        entity = _entity(extra={"owner": "Carol"})
        assert _eval(_condition("owner", "ilike", "car%"), entity).matched is True
        assert _eval(_condition("owner", "ilike", "CAR%"), entity).matched is True

    def test_missing_attribute_no_match(self) -> None:
        assert _eval(_condition("owner", "ilike", "car%"), _entity(extra={})).matched is False


class TestOperandKinds:
    def test_parameter_operand(self) -> None:
        condition = AttributeCondition(
            attribute="owner", comparator="not_in", value=ValueRef(kind="parameter", parameter="excluded")
        )
        entity = _entity(extra={"owner": "carol"})
        environment = EvaluationEnvironment(parameters={"excluded": ["alice", "bob"]})
        assert _eval(condition, entity, environment=environment).matched is True

    def test_binding_operand(self) -> None:
        condition = AttributeCondition(
            attribute="owner", comparator="not_in", value=ValueRef(kind="binding", binding="excluded")
        )
        entity = _entity(extra={"owner": "carol"})
        environment = EvaluationEnvironment(bindings={"excluded": ("alice", "bob")})
        assert _eval(condition, entity, environment=environment).matched is True

    def test_attribute_of_self_operand_with_like(self) -> None:
        condition = AttributeCondition(
            attribute="owner", comparator="like", value=ValueRef(kind="attribute_of_self", attribute="owner_pattern")
        )
        entity = _entity(extra={"owner": "carol", "owner_pattern": "car%"})
        assert _eval(condition, entity).matched is True
