"""Read-only connection routes registered by the main connections router."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.rendering.diagram_selection import connections_among
from src.infrastructure.rest.contracts.authoring_catalogs import (
    OntologyClassificationResponse,
    OntologyPairResponse,
    RelationNotationsResponse,
)
from src.infrastructure.rest.contracts.connections import ConnectionListResponse
from src.infrastructure.rest.contracts.entities import EntityNeighborhoodResponse
from src.infrastructure.rest.contracts.errors import ApiError, FieldError, ValidationErrorDetails
from src.infrastructure.rest.contracts.search import KeywordSearchResponse
from src.infrastructure.rest.contracts.write_help import WriteHelpResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._failures import derivation_limit
from src.infrastructure.rest.routers._global_search import (
    filter_global_hits,
    hidden_diagram_entity_types,
    prioritize_global_hits,
)
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_CONNECTIONS,
    TAG_ENTITIES,
    TAG_TAXONOMY,
)
from src.infrastructure.rest.routers._search_hits import search_hit_to_dict
from src.infrastructure.rest.routers.connections.neighbors import DerivationLimitError, derive_neighbor_response


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

    @router.get("/api/connections/among", tags=[TAG_CONNECTIONS],
        summary="Connections with both endpoints in a set of entities",
        response_model=ConnectionListResponse)
    def get_connections_among(entity_ids: str) -> dict[str, Any]:
        """The model's connections among these entities — the induced subgraph over the set.

        What a picture of a set of elements draws without being told: a connection with one
        endpoint outside the set has nothing to attach to. Served as one read rather than as a
        star per node, because a caller assembling it from stars gets an answer that depends on
        which nodes it happened to ask about — an edge between two of them is incident to neither
        of the ones it asked for, so it is never in any response and nothing filters it out.

        The same invariant a viewpoint's population already states, and the same rule a diagram's
        membership already resolves; this exposes it once rather than adding a third reading.

        ``entity_ids`` is comma-separated, and unknown ids simply match nothing: the caller is
        naming a set to look within, not addressing a resource that must exist.
        """
        wanted = [entity_id.strip() for entity_id in entity_ids.split(",") if entity_id.strip()]
        repo = s.get_repo()
        found = [
            connection
            for connection_id in connections_among(repo, wanted)
            if (connection := repo.get_connection(connection_id)) is not None
        ]
        return {"items": [s.connection_to_dict(connection) for connection in found]}

    @router.get("/api/entities/{artifact_id}/neighbors", tags=[TAG_CONNECTIONS],
        summary="Neighbouring entities of an entity",
        response_model=EntityNeighborhoodResponse, responses=READ_RESPONSES)
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
            raise derivation_limit(str(exc)) from exc

    @router.get("/api/search", tags=[TAG_ENTITIES], summary="Keyword search over artifacts",
        response_model=KeywordSearchResponse)
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
        return {"query": result.query, "hits": [search_hit_to_dict(hit) for hit in hits]}

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

    @router.get("/api/ontology/classification", tags=[TAG_CONNECTIONS],
        summary="What one entity type may connect to", response_model=OntologyClassificationResponse)
    def get_ontology_classification(
        source_type: str,
        source_id: str | None = None,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, Any]:
        # Split from `/api/ontology/pairs`. One address used to answer both questions, choosing its
        # response shape by whether `target_type` was supplied, so no schema could describe it — and an
        # invalid endpoint came back as a 200 carrying an `error` string, a whole-operation failure
        # wearing a success code. That rationale lives here rather than in the docstring because
        # FastAPI serves the docstring as the OpenAPI `description`, where it described a parameter
        # this operation does not have and left readers of /docs looking for `target_type`.
        """Every relationship available from this entity type, grouped by direction.

        For what may be drawn between an ordered *pair* of types, use `/api/ontology/pairs`.

        `source_id` is optional and does not narrow the answer — it corrects what the answer is about.
        Given the id of a global-artifact reference, the governing type is the type of the entity it
        *references* rather than the internal proxy type `source_type` names, and a caller cannot know
        that without asking. Naming a document or diagram reference is refused (422) rather than
        answered about the wrong type.
        """
        source, source_invalid = _resolve_effective_type(source_id, source_type, catalogs)
        if source_invalid:
            raise _not_a_connection_endpoint("source_id")
        return {"source_type": source_type, **catalogs.connections.classify_connections(source)}

    @router.get("/api/ontology/pairs", tags=[TAG_CONNECTIONS],
        summary="Relationship types permitted between two entity types",
        response_model=OntologyPairResponse)
    def get_ontology_pair(
        source_type: str,
        target_type: str,
        source_id: str | None = None,
        target_id: str | None = None,
        catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
    ) -> dict[str, Any]:
        # `target_type` is required here, which is the point of the split: it is not a filter that
        # narrows the classification, it selects a different question with a different answer.
        """What may be drawn between this ordered pair of entity types.

        For everything reachable from a single type, use `/api/ontology/classification`.

        `source_id` and `target_id` are optional and resolve global-artifact references to the type of
        the entity referenced, as on the classification read; either naming a document or diagram
        reference is refused (422).
        """
        source, source_invalid = _resolve_effective_type(source_id, source_type, catalogs)
        target, target_invalid = _resolve_effective_type(target_id, target_type, catalogs)
        if source_invalid:
            raise _not_a_connection_endpoint("source_id")
        if target_invalid:
            raise _not_a_connection_endpoint("target_id")
        connection_types = catalogs.connections.permissible_connection_types(source, target)
        return {
            "source_type": source_type,
            "target_type": target_type,
            "connection_types": list(connection_types),
            "symmetric": [item for item in connection_types if catalogs.connections.is_symmetric(item)],
            "relationship_kind_map": {
                item: catalogs.connections.relationship_kind(item) for item in connection_types
            },
        }

    @router.get("/api/write-help", tags=[TAG_TAXONOMY], summary="Catalog of writable types",
        response_model=WriteHelpResponse)
    def get_write_help() -> dict[str, Any]:
        from src.infrastructure.write.artifact_write.help import write_help

        return write_help()


def _not_a_connection_endpoint(field: str) -> ApiError:
    """A document or diagram reference named as a connection endpoint.

    422 rather than the 200-with-an-error-string this used to answer: the whole operation failed, and a
    success status carrying an error is only defensible for a mixed result that says which parts
    succeeded. Nothing here succeeded.
    """
    message = (
        "document/diagram global-artifact-references are not valid connection endpoints"
    )
    return ApiError(
        422, "validation_error", message,
        ValidationErrorDetails(field_errors=[FieldError(field=field, message=message)]),
    )

def _resolve_effective_type(
        artifact_id: str | None, declared_type: str, catalogs: RuntimeCatalogs
    ) -> tuple[str, bool]:
    if artifact_id is None:
        return declared_type, False
    repo = s.maybe_get_repo()
    if repo is None:
        return declared_type, False
    record = repo.get_entity(artifact_id)
    if record is None or not is_internal_entity_type(record.artifact_type, catalogs.ontology):
        return declared_type, False
    if record.extra.get("global-artifact-type") != "entity":
        return declared_type, True
    entity_type = record.extra.get("global-artifact-entity-type")
    return (entity_type if isinstance(entity_type, str) and entity_type else declared_type), False
