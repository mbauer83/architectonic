"""Read-only connection routes registered by the main connections router."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.contracts.authoring_catalogs import RelationNotationsResponse
from src.infrastructure.gui.contracts.connections import ConnectionListResponse
from src.infrastructure.gui.contracts.entities import DerivedNeighborhood, DirectNeighborhood
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._global_search import (
    filter_global_hits,
    hidden_diagram_entity_types,
    prioritize_global_hits,
)
from src.infrastructure.gui.routers._openapi import (
    READ_RESPONSES,
    TAG_CONNECTIONS,
    TAG_ENTITIES,
    TAG_TAXONOMY,
    OpenMapResponse,
)
from src.infrastructure.gui.routers.connection_neighbors import DerivationLimitError, derive_neighbor_response


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def register_connection_read_routes(router: APIRouter) -> None:
    """Attach read endpoints while keeping the write router within the file-size limit."""

    @router.get("/api/connections", tags=[TAG_CONNECTIONS], summary="List connections (AND-filtered)",
        response_model=ConnectionListResponse)
    def get_connections(
        entity_id: str,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> dict[str, Any]:
        conns = s.get_repo().find_connections_for(entity_id, direction=direction, conn_type=conn_type)
        # An object rather than a bare array: a top-level array has nowhere to put a total or a
        # cursor without becoming a breaking change later.
        return {"items": [s.connection_to_dict(c) for c in conns]}

    @router.get("/api/entities/{artifact_id}/neighbors", tags=[TAG_CONNECTIONS],
        summary="Neighbouring entities of an entity",
        response_model=DirectNeighborhood | DerivedNeighborhood, responses=READ_RESPONSES)
    def get_neighbors(
        artifact_id: str,
        max_hops: int = 1,
        traversal: Literal["direct", "derived"] = "direct",
        include_potential: bool = False,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, object]:
        """The neighbourhood of one entity, tagged by how it was reached.

        ``traversal`` is an alternate execution specification, so it stays in the query — but the
        two answers are genuinely different shapes, and the direct arm used to carry no tag at all,
        so a client could not tell which it had received.
        """
        entity_id = artifact_id
        repo = s.get_repo()
        if repo.get_entity(entity_id) is None:
            # Identity is in the path now, so an unknown id is an unaddressable resource rather
            # than a filter that matched nothing — and an empty neighbourhood is indistinguishable
            # from a real one with no neighbours, which is the wrong answer to give.
            raise HTTPException(404, f"Not found: {entity_id!r}")
        if traversal == "direct":
            hops = repo.find_neighbors(entity_id, max_hops=max_hops)
            return {"traversal": "direct", "hops": {hop: sorted(ids) for hop, ids in hops.items()}}
        try:
            return derive_neighbor_response(
                entity_id,
                max_hops=max_hops,
                include_potential=include_potential,
                read_access=repo,
                catalogs=catalogs,
            )
        except DerivationLimitError as exc:
            raise HTTPException(400, {"code": "derivation-limit", "path": "query", "message": str(exc)}) from exc

    @router.get("/api/search", tags=[TAG_ENTITIES], summary="Keyword search over artifacts",
        response_model=OpenMapResponse)
    def search(
        q: str,
        limit: int = 20,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, Any]:
        result = s.get_repo().search_artifacts(
            q,
            limit=limit * 3,
            include_connections=False,
            excluded_entity_types=hidden_diagram_entity_types(catalogs),
        )
        visible_hits = filter_global_hits(result.hits, catalogs)
        hits = prioritize_global_hits(visible_hits)[:limit]
        return {"query": result.query, "hits": [s.search_hit_to_dict(hit) for hit in hits]}

    @router.get("/api/relation-notations", tags=[TAG_CONNECTIONS],
        summary="How each relationship type is drawn", response_model=RelationNotationsResponse)
    def get_relation_notations(
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, Any]:
        """Line style and end markers per connection type, from the ontology.

        Served whole: a graph surface styles hundreds of edges spanning every relationship type
        it happens to meet, and a request per type would be a request per edge in the worst
        case. The shapes are structural ("hollow triangle at the target"), never named after the
        relationship, so a renderer can honour them without knowing this ontology's vocabulary.
        """
        return {"notations": catalogs.connections.all_relation_notations()}

    @router.get("/api/ontology", tags=[TAG_CONNECTIONS], summary="Ontology classification / permitted pairs",
        response_model=OpenMapResponse)
    def get_ontology(
        source_type: str,
        target_type: str | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, Any]:
        source, source_invalid = _resolve_effective_type(source_id, source_type)
        target, target_invalid = _resolve_effective_type(target_id, target_type or "")
        if source_invalid or target_invalid:
            return {
                "source_type": source_type,
                "target_type": target_type,
                "connection_types": [],
                "error": "document/diagram global-artifact-references are not valid connection endpoints",
            }
        if target:
            connection_types = catalogs.connections.permissible_connection_types(source, target)
            return {
                "source_type": source_type,
                "target_type": target_type,
                "connection_types": connection_types,
                "symmetric": [item for item in connection_types if catalogs.connections.is_symmetric(item)],
                "relationship_kind_map": {
                    item: catalogs.connections.relationship_kind(item) for item in connection_types
                },
            }
        return {"source_type": source_type, **catalogs.connections.classify_connections(source)}

    @router.get("/api/write-help", tags=[TAG_TAXONOMY], summary="Catalog of writable types",
        response_model=OpenMapResponse)
    def get_write_help() -> dict[str, Any]:
        from src.infrastructure.write.artifact_write.help import write_help

        return write_help()


def _resolve_effective_type(artifact_id: str | None, declared_type: str) -> tuple[str, bool]:
    if artifact_id is None:
        return declared_type, False
    repo = s.maybe_get_repo()
    if repo is None:
        return declared_type, False
    record = repo.get_entity(artifact_id)
    if record is None or not is_internal_entity_type(record.artifact_type, _catalogs().ontology):
        return declared_type, False
    if record.extra.get("global-artifact-type") != "entity":
        return declared_type, True
    entity_type = record.extra.get("global-artifact-entity-type")
    return (entity_type if isinstance(entity_type, str) and entity_type else declared_type), False
