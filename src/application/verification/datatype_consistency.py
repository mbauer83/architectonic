"""Correspondence predicate for the §3.2 bidirectional consistency rule.

A dt-* edge 'corresponds' to a backing model connection when:
  1. Both share the same relationship_kind.
  2. Their directions are compatible: symmetric dt types accept either
     direction; non-symmetric types require the same source→target order.

No dt-*→archimate-* mapping is hardcoded here.  Semantics are derived
entirely from ConnectionTypeInfo.relationship_kind and .symmetric.
"""

from __future__ import annotations

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo


def corresponds(
    dt_type: ConnectionTypeInfo,
    backing_type: ConnectionTypeInfo,
    same_direction: bool,
) -> bool:
    """True when a dt-* edge corresponds to a backing model connection.

    Args:
        dt_type: ConnectionTypeInfo for the diagram-owned dt-* connection.
        backing_type: ConnectionTypeInfo for the backing model connection.
        same_direction: True when the dt edge source's bound DOB is the
            backing edge's source; False when it is the backing edge's target.
    """
    if dt_type.relationship_kind is None or backing_type.relationship_kind is None:
        return False
    if dt_type.relationship_kind != backing_type.relationship_kind:
        return False
    return True if dt_type.symmetric else same_direction


def admissible_backing_kinds(dt_type: ConnectionTypeInfo) -> frozenset[str]:
    """Relationship kinds that a backing connection must carry to correspond to dt_type.

    Used by the verifier to populate Issue.details.permitted_backing_kinds
    without a hardcoded dt-*→archimate-* constant.
    """
    if dt_type.relationship_kind is None:
        return frozenset()
    return frozenset({dt_type.relationship_kind})
