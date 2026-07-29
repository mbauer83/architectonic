"""Serialization of ``TracePatternSet`` back to the persisted mapping form — the exact mirror
of ``viewpoint_trace_pattern_parsing`` so that domain → YAML → domain is an identity, and a
``{ref}`` is preserved rather than expanded (immutable value-expansion happens only at
evaluation, never on save)."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_trace_patterns import (
    Branches,
    BranchesRef,
    DerivedReachabilityLeaf,
    DiagnosticEdge,
    InlineBranches,
    LayerMembershipEndpoint,
    Leaf,
    LeafEndpoint,
    NoneLeaf,
    RegistryEndpoint,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)


def trace_patterns_to_list(patterns: TracePatternSet) -> list[dict[str, object]]:
    return [_pattern_to_mapping(p) for p in patterns.patterns]


def _pattern_to_mapping(pattern: TracePattern) -> dict[str, object]:
    out: dict[str, object] = {
        "name": pattern.name,
        "kind": pattern.kind,
        "applies_to": list(pattern.applies_to),
        "branches": _branches_to_mapping(pattern.branches),
    }
    if pattern.shortcuts:
        out["shortcuts"] = [_diagnostic_edge_to_mapping(s) for s in pattern.shortcuts]
    out["leaf"] = _leaf_to_mapping(pattern.leaf)
    if pattern.diagnostic:
        out["diagnostic"] = True
    return out


def _branches_to_mapping(branches: Branches) -> dict[str, object]:
    match branches:
        case BranchesRef(ref=ref):
            return {"ref": ref}
        case InlineBranches(edges=edges):
            return {named.label: _stored_edge_to_mapping(named.edge) for named in edges}


def _stored_edge_to_mapping(edge: StoredEdge) -> dict[str, object]:
    return {
        "kind": edge.kind,
        "connection": edge.connection,
        "direction": edge.direction,
        "endpoint": {"type": edge.endpoint_type},
    }


def _diagnostic_edge_to_mapping(edge: DiagnosticEdge) -> dict[str, object]:
    return {
        "kind": edge.kind,
        "connection": edge.connection,
        "direction": edge.direction,
        "endpoint": {"type": edge.endpoint_type},
        "status": edge.status,
    }


def _leaf_to_mapping(leaf: Leaf) -> dict[str, object]:
    match leaf:
        case NoneLeaf():
            return {"kind": leaf.kind}
        case DerivedReachabilityLeaf(connection=connection, traversal=traversal, max_hops=max_hops, endpoint=endpoint):
            return {
                "kind": leaf.kind,
                "connection": connection,
                "traversal": traversal,
                "max_hops": max_hops,
                "endpoint": _leaf_endpoint_to_mapping(endpoint),
            }


def _leaf_endpoint_to_mapping(endpoint: LeafEndpoint) -> dict[str, object]:
    match endpoint:
        case RegistryEndpoint(registry=registry):
            return {"registry": registry}
        case LayerMembershipEndpoint(domain=domain, entity_class=entity_class):
            return {"domain": domain} if entity_class is None else {"domain": domain, "class": entity_class}
