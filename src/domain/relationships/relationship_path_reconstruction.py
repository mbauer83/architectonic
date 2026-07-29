"""Pure reconstruction of one recorded relationship-derivation path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.relationship_derivation import DerivedStep, OrientedRelation, compose


class EntityReadAccess(Protocol):
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...


class RelationshipPathReadAccess(EntityReadAccess, Protocol):
    def get_connection(self, artifact_id: str) -> ConnectionRecord | None: ...


@dataclass(frozen=True)
class DerivedPathRelationship:
    source_id: str
    target_id: str
    connection_type: str
    certainty: Literal["certain", "potential"]
    hops: int


@dataclass(frozen=True)
class BrokenRelationshipPath:
    detail: str


@dataclass(frozen=True)
class NoLongerDerivedRelationship:
    reason: str


PathDerivationOutcome: TypeAlias = DerivedPathRelationship | BrokenRelationshipPath | NoLongerDerivedRelationship


def derive_relationship_for_path(
    path_key: str,
    *,
    read_access: RelationshipPathReadAccess,
    registries: ModuleCatalog,
) -> PathDerivationOutcome:
    """Re-apply relationship derivation to one canonical witness path."""
    parsed = _parse_path_key(path_key)
    if parsed is None:
        return BrokenRelationshipPath("path key must contain id@fwd or id@rev steps")
    entity_types = registries.all_entity_types()
    connection_types = registries.all_connection_types()
    relations: list[OrientedRelation] = []
    for connection_id, orientation in parsed:
        connection = read_access.get_connection(connection_id)
        if connection is None:
            return BrokenRelationshipPath(f"connection {connection_id!r} no longer exists")
        relation = oriented_relation(connection, read_access, entity_types, connection_types, orientation)
        if relation is None:
            return BrokenRelationshipPath(f"connection {connection_id!r} has a missing endpoint or unknown type")
        relations.append(relation)
    if len(relations) < 2:
        return NoLongerDerivedRelationship("a derived relationship needs at least two connections")
    rules = tuple(rule for ontology in registries.all_ontologies().values() for rule in ontology.derivation_rules)
    restrictions = tuple(
        rule for ontology in registries.all_ontologies().values() for rule in ontology.derivation_restrictions
    )
    current = relations[0]
    for next_relation in relations[1:]:
        intermediate = shared_entity_info(current, next_relation, read_access, entity_types)
        if intermediate is None:
            return BrokenRelationshipPath("recorded orientation no longer joins adjacent connections")
        step = compose(
            current,
            next_relation,
            intermediate,
            rules,
            registries.aggregated_permitted_relationships(),
            restrictions,
        )
        if step is None:
            return NoLongerDerivedRelationship("the resolved path no longer satisfies a derivation rule")
        current = _derived_relation(step)
    return DerivedPathRelationship(
        current.source_id,
        current.target_id,
        current.connection_type.artifact_type,
        "potential" if current.potential_steps else "certain",
        len(relations),
    )


def oriented_relation(
    connection: ConnectionRecord,
    read_access: EntityReadAccess,
    entity_types: Mapping[EntityTypeName, EntityTypeInfo],
    connection_types: Mapping[ConnectionTypeName, ConnectionTypeInfo],
    orientation: Literal["forward", "reverse"] = "forward",
) -> OrientedRelation | None:
    source = read_access.get_entity(connection.source)
    target = read_access.get_entity(connection.target)
    connection_type = connection_types.get(ConnectionTypeName(connection.conn_type))
    if source is None or target is None or connection_type is None:
        return None
    source_info = entity_types.get(EntityTypeName(source.artifact_type))
    target_info = entity_types.get(EntityTypeName(target.artifact_type))
    if source_info is None or target_info is None or connection_type.derivation_role is None:
        return None
    return OrientedRelation(
        connection.artifact_id,
        connection_type,
        connection.source,
        connection.target,
        orientation,
        EntityTypeName(source.artifact_type),
        EntityTypeName(target.artifact_type),
        source_info,
        target_info,
    )


def shared_entity_info(
    first: OrientedRelation,
    second: OrientedRelation,
    read_access: EntityReadAccess,
    entity_types: Mapping[EntityTypeName, EntityTypeInfo],
) -> EntityTypeInfo | None:
    shared = {first.source_id, first.target_id} & {second.source_id, second.target_id}
    if len(shared) != 1:
        return None
    entity = read_access.get_entity(shared.pop())
    return entity_types.get(EntityTypeName(entity.artifact_type)) if entity is not None else None


def _derived_relation(step: DerivedStep) -> OrientedRelation:
    return OrientedRelation(
        f"derived:{step.connection_type.artifact_type}",
        step.connection_type,
        step.source_id,
        step.target_id,
        source_type=EntityTypeName(step.source_info.artifact_type) if step.source_info is not None else None,
        target_type=EntityTypeName(step.target_info.artifact_type) if step.target_info is not None else None,
        source_info=step.source_info,
        target_info=step.target_info,
        potential_steps=step.potential_steps,
    )


def _parse_path_key(path_key: str) -> tuple[tuple[str, Literal["forward", "reverse"]], ...] | None:
    if not path_key:
        return None
    steps: list[tuple[str, Literal["forward", "reverse"]]] = []
    for item in path_key.split("|"):
        connection_id, separator, marker = item.rpartition("@")
        if not connection_id or separator != "@" or marker not in {"fwd", "rev"}:
            return None
        steps.append((connection_id, "forward" if marker == "fwd" else "reverse"))
    return tuple(steps)
