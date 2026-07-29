"""Execution-scoped graph index for branch-complete trace evaluation.

Built ONCE per execution and shared across every row and pattern — the deliberate answer to
the rescan-per-row cost that makes the ad-hoc coverage view slow. It holds:

* a direct adjacency index over ONLY the connection types the patterns reference, keyed
  ``(node, conn_type) -> neighbours`` in both directions (branch enumeration is direct-stored
  edges only — derived edges would collapse the very branches this view quantifies over);
* per-entity type / domain / status maps and per-type class memberships (for leaf layer
  membership and the deprecated/retired scope policy);
* a per-requirement realizer closure = direct incoming realization UNION the result of ONE
  batched ``derive_relationships`` call over all requirement anchors (derived relationships are
  ≥2-hop and returned one-per-pair, so the direct 1-hop edges must be added from the index).

Complexity: O(E) to build adjacency (``connection_ids`` + O(1) ``get_connection``, never a
per-entity query), O(N) for the entity maps, and ONE bounded derivation pass; leaf coverage is
then a memoised set lookup per requirement reused by every row/pattern.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from src.application.viewpoints.ports import RepositoryReadAccess
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    RelationshipDerivationRequest,
    derive_relationships,
)

REALIZATION_CONNECTION = "archimate-realization"


@dataclass(frozen=True)
class TraceGraphIndex:
    incoming: Mapping[tuple[str, str], tuple[str, ...]]  # (target, conn_type) -> source ids
    outgoing: Mapping[tuple[str, str], tuple[str, ...]]  # (source, conn_type) -> target ids
    type_of: Mapping[str, str]
    domain_of: Mapping[str, str]
    status_of: Mapping[str, str]
    name_of: Mapping[str, str]
    classes_by_type: Mapping[str, frozenset[str]]
    enterprise_ids: frozenset[str]
    derived_realizers: Mapping[str, frozenset[str]]  # requirement id -> derived realizer source ids
    derived_truncated: bool

    def sources(self, target: str, conn_type: str) -> tuple[str, ...]:
        """Entities with a stored ``conn_type`` edge INTO ``target`` (reverse adjacency)."""
        return self.incoming.get((target, conn_type), ())

    def targets(self, source: str, conn_type: str) -> tuple[str, ...]:
        """Entities a stored ``conn_type`` edge FROM ``source`` points at."""
        return self.outgoing.get((source, conn_type), ())

    def realizers_of(self, requirement_id: str) -> frozenset[str]:
        """All elements realizing ``requirement_id`` via a direct or derived (≤hop-cap)
        realization chain — the leaf denominator, tested by membership against a target set."""
        direct = self.incoming.get((requirement_id, REALIZATION_CONNECTION), ())
        return frozenset(direct) | self.derived_realizers.get(requirement_id, frozenset())

    def is_active(self, entity_id: str) -> bool:
        """A row/branch node participates unless deprecated or retired."""
        return self.status_of.get(entity_id, "") not in ("deprecated", "retired")


def build_trace_graph_index(
    read_access: RepositoryReadAccess,
    registries: ModuleCatalog,
    *,
    referenced_connection_types: frozenset[str],
    requirement_type: str,
    bounds: DerivationBounds,
) -> TraceGraphIndex:
    incoming: dict[tuple[str, str], list[str]] = defaultdict(list)
    outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
    for connection_id in read_access.connection_ids():
        connection = read_access.get_connection(connection_id)
        if connection is None or connection.conn_type not in referenced_connection_types:
            continue
        incoming[(connection.target, connection.conn_type)].append(connection.source)
        outgoing[(connection.source, connection.conn_type)].append(connection.target)

    type_of: dict[str, str] = {}
    domain_of: dict[str, str] = {}
    status_of: dict[str, str] = {}
    name_of: dict[str, str] = {}
    requirement_ids: list[str] = []
    for entity_id in read_access.entity_ids():
        record = read_access.get_entity(entity_id)
        if record is None:
            continue
        type_of[entity_id] = record.artifact_type
        domain_of[entity_id] = str(record.domain)
        status_of[entity_id] = record.status
        name_of[entity_id] = record.name
        if record.artifact_type == requirement_type:
            requirement_ids.append(entity_id)

    classes_by_type = {
        str(name): frozenset(info.classes) for name, info in registries.all_entity_types().items()
    }
    derived_realizers, truncated = _derived_realizer_closure(
        read_access, registries, requirement_ids=frozenset(requirement_ids), bounds=bounds
    )
    return TraceGraphIndex(
        incoming={key: tuple(value) for key, value in incoming.items()},
        outgoing={key: tuple(value) for key, value in outgoing.items()},
        type_of=type_of,
        domain_of=domain_of,
        status_of=status_of,
        name_of=name_of,
        classes_by_type=classes_by_type,
        enterprise_ids=frozenset(read_access.enterprise_entity_ids()),
        derived_realizers=derived_realizers,
        derived_truncated=truncated,
    )


def _derived_realizer_closure(
    read_access: RepositoryReadAccess,
    registries: ModuleCatalog,
    *,
    requirement_ids: frozenset[str],
    bounds: DerivationBounds,
) -> tuple[Mapping[str, frozenset[str]], bool]:
    """ONE batched derivation over all requirement anchors → per-requirement derived realizer
    source ids. Filtered to realization edges incident (as target) to a requirement."""
    if not requirement_ids:
        return {}, False
    result = derive_relationships(
        RelationshipDerivationRequest(
            anchors=requirement_ids, direction="incoming", certainty="certain_only", bounds=bounds
        ),
        read_access=read_access,
        registries=registries,
    )
    realizers: dict[str, set[str]] = defaultdict(set)
    for relationship in result.relationships:
        if relationship.connection_type == REALIZATION_CONNECTION and relationship.target_id in requirement_ids:
            realizers[relationship.target_id].add(relationship.source_id)
    return {key: frozenset(value) for key, value in realizers.items()}, result.truncated
