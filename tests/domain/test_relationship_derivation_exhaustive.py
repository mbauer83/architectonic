"""Metamodel-wide composition checks derived from direct relationship inputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping, cast

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.relationship_derivation import OrientedRelation, compose
from src.ontologies.archimate_4 import module
from tests.fixtures.viewpoints.derivation_rules_independent_encoding import COMPOSITION_RULES


@dataclass(frozen=True)
class _DirectRelation:
    source_type: EntityTypeName
    target_type: EntityTypeName
    connection_type: ConnectionTypeInfo


def _direct_relations() -> tuple[_DirectRelation, ...]:
    return tuple(
        _DirectRelation(source, target, module.connection_types[connection])
        for source, pairs in sorted(module.permitted_relationships.by_source().items())
        for target, connection in sorted(pairs)
        if module.connection_types[connection].derivation_role is not None
    )


def _joined_pairs() -> Iterable[tuple[_DirectRelation, _DirectRelation, str, EntityTypeInfo]]:
    relations = _direct_relations()
    by_source: dict[EntityTypeName, list[_DirectRelation]] = defaultdict(list)
    by_target: dict[EntityTypeName, list[_DirectRelation]] = defaultdict(list)
    for relation in relations:
        by_source[relation.source_type].append(relation)
        by_target[relation.target_type].append(relation)
    for first in relations:
        for second in by_source[first.target_type]:
            yield first, second, "target-source", module.entity_types[first.target_type]
        for second in by_target[first.target_type]:
            yield first, second, "target-target", module.entity_types[first.target_type]
        for second in by_source[first.source_type]:
            yield first, second, "source-source", module.entity_types[first.source_type]
        for second in by_target[first.source_type]:
            yield first, second, "source-target", module.entity_types[first.source_type]


def _relation(item: _DirectRelation, *, source_id: str, target_id: str) -> OrientedRelation:
    return OrientedRelation(
        f"{item.source_type}:{item.connection_type.artifact_type}:{item.target_type}",
        item.connection_type,
        source_id,
        target_id,
        source_type=item.source_type,
        target_type=item.target_type,
        source_info=module.entity_types[item.source_type],
        target_info=module.entity_types[item.target_type],
    )


def _oriented_pair(
    first: _DirectRelation, second: _DirectRelation, join: str
) -> tuple[OrientedRelation, OrientedRelation]:
    if join == "target-source":
        return _relation(first, source_id="a", target_id="b"), _relation(second, source_id="b", target_id="c")
    if join == "target-target":
        return _relation(first, source_id="a", target_id="b"), _relation(second, source_id="c", target_id="b")
    if join == "source-source":
        return _relation(first, source_id="a", target_id="b"), _relation(second, source_id="a", target_id="c")
    return _relation(first, source_id="a", target_id="b"), _relation(second, source_id="c", target_id="a")


def _claimed_intermediate_classes() -> frozenset[str]:
    """Intermediate classes the transcription claims by name — the loader derives the same set."""
    return frozenset(
        str(rule["intermediate_class"]) for rule in COMPOSITION_RULES if rule.get("intermediate_class") is not None
    )


def _expected_rule(
    first: _DirectRelation, second: _DirectRelation, join: str, intermediate: EntityTypeInfo
) -> Mapping[str, object] | None:
    for rule in COMPOSITION_RULES:
        if rule["first_role"] != first.connection_type.derivation_role:
            continue
        if rule["second_role"] != second.connection_type.derivation_role:
            continue
        if rule.get("join", "target-source") != join:
            continue
        if rule.get("first_artifact_type") not in {None, first.connection_type.artifact_type}:
            continue
        if rule.get("second_artifact_type") not in {None, second.connection_type.artifact_type}:
            continue
        types = rule.get("second_artifact_types", ())
        assert isinstance(types, tuple)
        if types and second.connection_type.artifact_type not in types:
            continue
        if rule.get("intermediate_artifact_type") not in {None, intermediate.artifact_type}:
            continue
        # A class some rule claims by name is a class the generic rules do not compose across, and a
        # rule that claims one joins relationships of ONE type. This matcher is a second implementation
        # of the same dispatch — that is what makes the comparison independent — so it derives the
        # exclusivity from the transcription exactly as the loader derives it from the YAML, rather than
        # naming any class here.
        intermediate_class = rule.get("intermediate_class")
        if intermediate_class is not None and intermediate_class not in intermediate.classes:
            continue
        if intermediate_class is None and _claimed_intermediate_classes() & set(intermediate.classes):
            continue
        if rule.get("requires_same_connection_type", False) and (
            first.connection_type.artifact_type != second.connection_type.artifact_type
        ):
            continue
        return cast(Mapping[str, object], rule)
    return None


def _expected_connection_type(
    rule: Mapping[str, object], first: _DirectRelation, second: _DirectRelation
) -> ConnectionTypeInfo | None:
    result = rule["result"]
    if result in {"first", "specialization", "triggering"}:
        return first.connection_type
    if result in {"second", "flow"}:
        return second.connection_type
    if first.connection_type.derivation_strength is None or second.connection_type.derivation_strength is None:
        return None
    return (
        first.connection_type
        if first.connection_type.derivation_strength <= second.connection_type.derivation_strength
        else second.connection_type
    )


def test_every_composition_from_direct_inputs_has_the_specified_result_shape() -> None:
    observed = 0
    for first, second, join, intermediate in _joined_pairs():
        expected = _expected_rule(first, second, join, intermediate)
        result = compose(
            *_oriented_pair(first, second, join),
            intermediate,
            module.derivation_rules,
            module.permitted_relationships,
            module.derivation_restrictions,
        )
        if expected is None:
            assert result is None
            continue
        expected_type = _expected_connection_type(expected, first, second)
        if expected_type is None:
            assert result is None
            continue
        endpoint_ids = {
            "first-source": "a",
            "first-target": "b",
            "second-source": "b" if join == "target-source" else "c" if join != "source-source" else "a",
            "second-target": "c"
            if join in {"target-source", "source-source"}
            else "b"
            if join == "target-target"
            else "a",
        }
        source_endpoint = expected.get("result_source", "first-source")
        target_endpoint = expected.get("result_target", "second-target")
        assert isinstance(source_endpoint, str)
        assert isinstance(target_endpoint, str)
        if expected.get("requires_permitted_result", False) and not module.permitted_relationships.permits(
            _endpoint_type(source_endpoint, first, second),
            _endpoint_type(target_endpoint, first, second),
            ConnectionTypeName(expected_type.artifact_type),
        ):
            assert result is None
            continue
        if result is None:
            continue
        observed += 1
        assert result.certainty == expected["certainty"]
        assert result.connection_type == expected_type
        assert result.source_id == endpoint_ids[source_endpoint]
        assert result.target_id == endpoint_ids[target_endpoint]
    assert observed > 1_000


def _endpoint_type(endpoint: object, first: _DirectRelation, second: _DirectRelation) -> EntityTypeName:
    endpoints = {
        "first-source": first.source_type,
        "first-target": first.target_type,
        "second-source": second.source_type,
        "second-target": second.target_type,
    }
    assert isinstance(endpoint, str)
    return endpoints[endpoint]
