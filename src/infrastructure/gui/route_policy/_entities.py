"""Canonical route policy for the entity, connection and taxonomy surfaces.

An entity is a repository artifact with a stable short id, so its identity is a path
parameter and every per-entity projection hangs off that path. A connection has a composite
but single-segment id (``{src}---{tgt}@@{type}``, `domain/artifact_id.py:159`), so it is
addressed the same way; the connection *list* keeps ``entity_id`` in the query because
removing it returns the whole collection.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._types import STREAM, RouteRow

ENTITY_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/entities", "collection", "entities_list_entities", "EntityListResponse",
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "POST", "/api/entities", "collection", "entities_create_entity", "WriteResultResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}", "detail", "entities_read_entity", "EntityDetailResponse",
        identity_parameters=("artifact_id",), cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "PATCH", "/api/entities/{artifact_id}", "detail", "entities_update_entity", "WriteResultResponse",
        identity_parameters=("artifact_id",), mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/entities/{artifact_id}", "detail", "entities_delete_entity", "WriteResultResponse",
        identity_parameters=("artifact_id",), mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/context", "subresource", "entities_read_entity_context",
        "EntityContextResponse",
        identity_parameters=("artifact_id",), cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/neighbors", "subresource", "connections_read_entity_neighbors",
        "EntityNeighborhoodResponse",
        identity_parameters=("artifact_id",), cache_directive="no-cache", timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/display-item", "subresource", "diagrams_read_entity_display_item",
        "EntityDisplayItemResponse",
        identity_parameters=("artifact_id",), cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/entity-schemata/{artifact_type}", "detail", "entities_read_entity_schema",
        "EntitySchemaResponse",
        identity_parameters=("artifact_type",), cache_directive="no-cache",
    ),
)

CONNECTION_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/connections", "collection", "connections_list_connections", "ConnectionListResponse",
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "POST", "/api/connections", "collection", "connections_create_connection", "WriteResultResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/connections/{connection_id}", "detail", "connections_update_connection",
        "WriteResultResponse",
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/connections/{connection_id}", "detail", "connections_delete_connection",
        "WriteResultResponse",
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/connections/{connection_id}/associated-entities", "subresource",
        "connections_update_connection_associations", "WriteResultResponse",
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/connections/cleanup-broken-refs", "operation", "connections_cleanup_broken_references",
        "BrokenReferenceCleanupResponse",
        mutation_domain="repository", timeout_class="derived-graph",
    ),
)

SEARCH_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/search", "collection", "entities_search_artifacts", "KeywordSearchResponse",
        cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/artifact-search", "collection", "entities_search_display_artifacts",
        "ArtifactSearchResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/entity-display-search", "collection", "diagrams_search_entity_display_items",
        "EntityDisplaySearchResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/reference-search", "collection", "documents_search_reference_artifacts",
        "ReferenceSearchResponse", cache_directive="no-cache",
    ),
)

TAXONOMY_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/stats", "catalog", "taxonomy_read_repository_stats", "RepositoryStatsResponse",
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "GET", "/api/backend-identity", "catalog", "taxonomy_read_backend_identity",
        "BackendIdentityResponse", cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/entity-taxonomy", "catalog", "taxonomy_read_entity_taxonomy",
        "EntityTaxonomyResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/authoring-guidance", "catalog", "taxonomy_read_authoring_guidance",
        "AuthoringGuidanceResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/write-help", "catalog", "taxonomy_read_write_help", "WriteHelpResponse",
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/modules", "catalog", "taxonomy_list_modules", "ModuleRegistryResponse",
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/ontology", "catalog", "connections_read_ontology", "OntologyClassificationResponse",
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/relation-notations", "catalog", "connections_read_relation_notations",
        "RelationNotationResponse", cache_directive="private",
    ),
    RouteRow(
        "POST", "/api/identifiers/allocate", "operation", "entities_allocate_identifiers",
        "IdentifierAllocationResponse",
    ),
    RouteRow("GET", "/api/events", "stream", "events_stream_events", STREAM, timeout_class="streaming"),
)
