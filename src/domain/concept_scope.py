"""Reusable concept-scope predicates for diagram types and viewpoints."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo


@dataclass(frozen=True)
class HierarchyPredicate:
    """Predicate matching one hierarchy index against an allowed value set."""

    index: int
    values: frozenset[str]

    def admits(self, info: EntityTypeInfo) -> bool:
        return self.index < len(info.hierarchy) and info.hierarchy[self.index] in self.values


@dataclass(frozen=True)
class EndpointRule:
    """Optional endpoint narrowing for one connection type or for all connection types."""

    connection_type: ConnectionTypeName | None = None
    source_types: frozenset[EntityTypeName] | None = None
    target_types: frozenset[EntityTypeName] | None = None

    def applies_to(self, connection_type: ConnectionTypeName) -> bool:
        return self.connection_type is None or self.connection_type == connection_type

    def admits(
        self,
        source_type: EntityTypeName,
        target_type: EntityTypeName,
        connection_type: ConnectionTypeName,
    ) -> bool:
        if not self.applies_to(connection_type):
            return False
        if self.source_types is not None and source_type not in self.source_types:
            return False
        return self.target_types is None or target_type in self.target_types


@dataclass(frozen=True)
class ConceptScope:
    """Frozen admissibility rules for entity and connection concepts.

    ``None`` type sets mean "unrestricted". Empty frozensets are valid and mean
    "admits nothing" for that axis.

    ``excluded_*`` fields are a genuine subtraction, not a second allow-list: they carve
    exceptions out of whatever the include-side already admits (unrestricted or an
    explicit allow-list), including any entity/connection type added to the ontology
    *after* a scope was authored — unlike a plain enumerated exclude list frozen against
    today's known types, ``excluded_hierarchy_predicates`` (reusing the same predicate
    class as inclusion) keeps excluding a whole hierarchy branch (e.g. a domain) as new
    types are added under it. Composed via ``__and__`` as a union of both sides'
    exclusions: if either input scope would exclude a concept, so does the intersection.
    """

    entity_types: frozenset[EntityTypeName] | None = None
    entity_class_predicates: tuple[frozenset[str], ...] = ()
    hierarchy_predicates: tuple[HierarchyPredicate, ...] = ()
    connection_types: frozenset[ConnectionTypeName] | None = None
    endpoint_rules: tuple[EndpointRule, ...] = field(default_factory=tuple)
    excluded_entity_types: frozenset[EntityTypeName] = frozenset()
    excluded_hierarchy_predicates: tuple[HierarchyPredicate, ...] = ()
    excluded_connection_types: frozenset[ConnectionTypeName] = frozenset()

    def _entity_excluded(self, entity_type: EntityTypeName, info: EntityTypeInfo | None) -> bool:
        if entity_type in self.excluded_entity_types:
            return True
        if info is None:
            return False
        return any(predicate.admits(info) for predicate in self.excluded_hierarchy_predicates)

    def admits_entity_type(self, entity_type: EntityTypeName, info: EntityTypeInfo | None = None) -> bool:
        if self.entity_types is not None and entity_type not in self.entity_types:
            return False
        if self.entity_class_predicates or self.hierarchy_predicates:
            if info is None:
                return False
            if any(not classes.intersection(info.classes) for classes in self.entity_class_predicates):
                return False
            if not all(predicate.admits(info) for predicate in self.hierarchy_predicates):
                return False
        return not self._entity_excluded(entity_type, info)

    def admits_connection_type(self, connection_type: ConnectionTypeName) -> bool:
        if self.connection_types is not None and connection_type not in self.connection_types:
            return False
        return connection_type not in self.excluded_connection_types

    def admits_connection(
        self,
        source_type: EntityTypeName,
        target_type: EntityTypeName,
        connection_type: ConnectionTypeName,
    ) -> bool:
        if self.entity_types is not None and (
            source_type not in self.entity_types or target_type not in self.entity_types
        ):
            return False
        if self._entity_excluded(source_type, None) or self._entity_excluded(target_type, None):
            return False
        if not self.admits_connection_type(connection_type):
            return False
        applicable = tuple(rule for rule in self.endpoint_rules if rule.applies_to(connection_type))
        if not applicable:
            return True
        return any(rule.admits(source_type, target_type, connection_type) for rule in applicable)

    def admitted_entity_types(
        self,
        candidates: dict[EntityTypeName, EntityTypeInfo],
    ) -> dict[EntityTypeName, EntityTypeInfo]:
        return {
            entity_type: info
            for entity_type, info in candidates.items()
            if self.admits_entity_type(entity_type, info)
        }

    def admitted_connection_types[T](
        self,
        candidates: dict[ConnectionTypeName, T],
    ) -> dict[ConnectionTypeName, T]:
        return {
            connection_type: info
            for connection_type, info in candidates.items()
            if self.admits_connection_type(connection_type)
        }

    def __and__(self, other: "ConceptScope") -> "ConceptScope":
        return ConceptScope(
            entity_types=_intersect_optional(self.entity_types, other.entity_types),
            entity_class_predicates=self.entity_class_predicates + other.entity_class_predicates,
            hierarchy_predicates=_intersect_hierarchy_predicates(self.hierarchy_predicates, other.hierarchy_predicates),
            connection_types=_intersect_optional(self.connection_types, other.connection_types),
            endpoint_rules=_intersect_endpoint_rules(
                self.endpoint_rules,
                other.endpoint_rules,
                _intersect_optional(self.connection_types, other.connection_types),
            ),
            excluded_entity_types=self.excluded_entity_types | other.excluded_entity_types,
            excluded_hierarchy_predicates=self.excluded_hierarchy_predicates + other.excluded_hierarchy_predicates,
            excluded_connection_types=self.excluded_connection_types | other.excluded_connection_types,
        )

    @staticmethod
    def unrestricted() -> "ConceptScope":
        return ConceptScope()


def _intersect_optional[T](left: frozenset[T] | None, right: frozenset[T] | None) -> frozenset[T] | None:
    if left is None:
        return right
    if right is None:
        return left
    return left & right


def _intersect_hierarchy_predicates(
    left: tuple[HierarchyPredicate, ...],
    right: tuple[HierarchyPredicate, ...],
) -> tuple[HierarchyPredicate, ...]:
    by_index: dict[int, frozenset[str]] = {}
    ordered_indexes: list[int] = []
    for predicate in left + right:
        if predicate.index not in by_index:
            ordered_indexes.append(predicate.index)
            by_index[predicate.index] = predicate.values
        else:
            by_index[predicate.index] = by_index[predicate.index] & predicate.values
    return tuple(HierarchyPredicate(index, by_index[index]) for index in ordered_indexes)


def _intersect_endpoint_rules(
    left: tuple[EndpointRule, ...],
    right: tuple[EndpointRule, ...],
    connection_types: frozenset[ConnectionTypeName] | None,
) -> tuple[EndpointRule, ...]:
    if not left:
        return tuple(rule for rule in right if _rule_can_apply(rule, connection_types))
    if not right:
        return tuple(rule for rule in left if _rule_can_apply(rule, connection_types))
    combined: list[EndpointRule] = []
    for left_rule in left:
        for right_rule in right:
            rule = _combine_endpoint_rule(left_rule, right_rule)
            if rule is not None and _rule_can_apply(rule, connection_types):
                combined.append(rule)
    return tuple(combined)


def _combine_endpoint_rule(left: EndpointRule, right: EndpointRule) -> EndpointRule | None:
    matches, connection_type = _combine_connection_type(left.connection_type, right.connection_type)
    if not matches:
        return None
    source_types = _intersect_optional(left.source_types, right.source_types)
    target_types = _intersect_optional(left.target_types, right.target_types)
    if source_types == frozenset() or target_types == frozenset():
        return None
    return EndpointRule(
        connection_type=connection_type,
        source_types=source_types,
        target_types=target_types,
    )


def _combine_connection_type(
    left: ConnectionTypeName | None,
    right: ConnectionTypeName | None,
) -> tuple[bool, ConnectionTypeName | None]:
    if left is None:
        return True, right
    if right is None or left == right:
        return True, left
    return False, None


def _rule_can_apply(
    rule: EndpointRule,
    connection_types: frozenset[ConnectionTypeName] | None,
) -> bool:
    return connection_types is None or rule.connection_type is None or rule.connection_type in connection_types
