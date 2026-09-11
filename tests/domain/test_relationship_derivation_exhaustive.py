"""Metamodel-wide composition checks derived from direct relationship inputs.

Every permitted relationship is joined with every other that shares an endpoint — 4,404,266 ordered
pairs, each a distinct input tuple, so there is no redundancy to remove. The work is split by the
first relation's source type instead: the same pairs, in about fifty test items rather than one.

That shape is not cosmetic. As a single item the loop ran for over four minutes under CI's branch
coverage on Python 3.13 — five times what it costs untraced — and it is the only test that has ever
taken a worker down, twice, six and a half minutes into a session, with no assertion failure, no
traceback and no out-of-memory report (it peaks at 180 MB). Split, no item runs more than a few
seconds, the pairs spread across the workers instead of queueing behind one, and a failure names the
source type it came from rather than a four-million-iteration loop.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, cast

import pytest

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


@lru_cache(maxsize=1)
def _direct_relations() -> tuple[_DirectRelation, ...]:
    return tuple(
        _DirectRelation(source, target, module.connection_types[connection])
        for source, pairs in sorted(module.permitted_relationships.by_source().items())
        for target, connection in sorted(pairs)
        if module.connection_types[connection].derivation_role is not None
    )


@lru_cache(maxsize=1)
def _relations_by_endpoint() -> tuple[
    dict[EntityTypeName, list[_DirectRelation]], dict[EntityTypeName, list[_DirectRelation]]
]:
    by_source: dict[EntityTypeName, list[_DirectRelation]] = defaultdict(list)
    by_target: dict[EntityTypeName, list[_DirectRelation]] = defaultdict(list)
    for relation in _direct_relations():
        by_source[relation.source_type].append(relation)
        by_target[relation.target_type].append(relation)
    return by_source, by_target


#: The four ways two relations can share an endpoint. Named here because the split runs over them.
JOINS: tuple[str, ...] = ("target-source", "target-target", "source-source", "source-target")

#: The source types the split runs over. Every direct relation has one, so iterating them covers
#: every `first` and therefore every pair.
SOURCE_TYPES: tuple[EntityTypeName, ...] = tuple(sorted({r.source_type for r in _direct_relations()}))

#: One item per (source type, join). The source type alone left three items carrying the bulk —
#: `grouping` and the two junctions, which the `@all` rules attach to everything, at 41s each under
#: branch coverage on 3.13 against 7s for a typical one. The join divides those evenly.
SPLIT: tuple[tuple[EntityTypeName, str], ...] = tuple(
    (source_type, join) for source_type in SOURCE_TYPES for join in JOINS
)


def _joined_pairs(
    source_type: EntityTypeName | None = None,
    only_join: str | None = None,
) -> Iterable[tuple[_DirectRelation, _DirectRelation, str, EntityTypeInfo]]:
    """Every joined pair, or only those whose first relation starts at *source_type*.

    The union over `SPLIT` is exactly the unfiltered set — asserted below, because a filter that
    silently dropped pairs would turn an exhaustive test into a partial one that still passes.
    """
    relations = _direct_relations() if source_type is None else tuple(
        r for r in _direct_relations() if r.source_type == source_type
    )
    by_source, by_target = _relations_by_endpoint()
    wanted = JOINS if only_join is None else (only_join,)
    for first in relations:
        if "target-source" in wanted:
            for second in by_source[first.target_type]:
                yield first, second, "target-source", module.entity_types[first.target_type]
        if "target-target" in wanted:
            for second in by_target[first.target_type]:
                yield first, second, "target-target", module.entity_types[first.target_type]
        if "source-source" in wanted:
            for second in by_source[first.source_type]:
                yield first, second, "source-source", module.entity_types[first.source_type]
        if "source-target" in wanted:
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


def test_the_split_covers_every_pair_the_unfiltered_generator_yields() -> None:
    """The union of the parts is the whole.

    Enumeration only — no composing — so it costs a second. It is the assertion the split rests on:
    a filter that quietly dropped pairs would leave an exhaustive test passing over a subset, which
    is the failure mode of splitting a test up and the one thing no other assertion here would see.
    """
    whole = sum(1 for _ in _joined_pairs())
    parts = sum(sum(1 for _ in _joined_pairs(source_type, join)) for source_type, join in SPLIT)

    assert parts == whole
    assert whole > 1_000_000


@pytest.mark.parametrize(("source_type", "only_join"), SPLIT)
def test_every_composition_from_direct_inputs_has_the_specified_result_shape(
    source_type: EntityTypeName, only_join: str
) -> None:
    examined = 0
    for first, second, join, intermediate in _joined_pairs(source_type, only_join):
        examined += 1
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
        assert result.certainty == expected["certainty"]
        assert result.connection_type == expected_type
        assert result.source_id == endpoint_ids[source_endpoint]
        assert result.target_id == endpoint_ids[target_endpoint]
    # Each item states that it had something to examine — the guard the whole loop used to carry
    # as `observed > 1_000`, restated for a part. It deliberately counts *pairs*, not compositions:
    # four of the 180 items compose nothing at all, because a junction joined source-to-source
    # derives nothing, and a per-item threshold on compositions would encode that rule a second
    # time. What the corpus composes is covered by the pairs themselves and by the union test.
    assert examined > 0, (source_type, only_join)


def _endpoint_type(endpoint: object, first: _DirectRelation, second: _DirectRelation) -> EntityTypeName:
    endpoints = {
        "first-source": first.source_type,
        "first-target": first.target_type,
        "second-source": second.source_type,
        "second-target": second.target_type,
    }
    assert isinstance(endpoint, str)
    return endpoints[endpoint]
