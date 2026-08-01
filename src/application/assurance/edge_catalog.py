"""Edge-type catalog for assurance authoring surfaces.

Serves the loaded assurance module's configuration — edge types, the exhaustive
permitted-relationship matrix, and the disjoint arch-reference type catalog —
so no authoring surface carries its own literal list. This reads module
configuration, not store content: surfaces may expose it when the assurance
capability is configured, without requiring the store to be unlocked.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet


@runtime_checkable
class EdgeCatalogSource(Protocol):
    """The module surface the catalog needs (satisfied by the assurance module)."""

    @property
    def connection_types(self) -> dict[Any, ConnectionTypeInfo]: ...

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet: ...

    @property
    def reference_types(self) -> dict[str, str]: ...


def build_edge_catalog(module: EdgeCatalogSource) -> dict[str, Any]:
    """One catalog payload: edge types and reference types are DISTINGUISHED —
    a reference type must never be submittable as an edge type (they are
    disjoint by module invariant) — and the matrix is grouped per type pair so
    a picker can filter to the legal set for one (source, target) pair."""
    edge_types = [
        {"name": str(name), "label": info.conn_lang}
        for name, info in sorted(module.connection_types.items(), key=lambda kv: str(kv[0]))
    ]
    pairs: dict[tuple[str, str], list[str]] = {}
    for source_type, entries in module.permitted_relationships.by_source().items():
        for target_type, connection_type in entries:
            pairs.setdefault((str(source_type), str(target_type)), []).append(str(connection_type))
    permitted = [
        {
            "source_type": source_type,
            "target_type": target_type,
            "connection_types": sorted(conn_types),
        }
        for (source_type, target_type), conn_types in sorted(pairs.items())
    ]
    reference_types = [
        {"name": name, "description": description}
        for name, description in sorted(module.reference_types.items())
    ]
    return {
        "edge_types": edge_types,
        "permitted": permitted,
        "reference_types": reference_types,
    }


def legal_connection_types_for(module: EdgeCatalogSource) -> Callable[[str, str], frozenset[str]]:
    """The per-pair legal set as a plain callable, for injection into the edge
    mutation — mutation code depends on this signature, never on module types."""
    def _legal(source_type: str, target_type: str) -> frozenset[str]:
        return frozenset(
            str(conn) for conn in module.permitted_relationships.permitted_connection_types(
                EntityTypeName(source_type), EntityTypeName(target_type),
            )
        )
    return _legal
