"""Canonical route policy for the entity, connection and taxonomy surfaces.

An entity is a repository artifact with a stable short id, so its identity is a path
parameter and every per-entity projection hangs off that path. A connection has a composite
but single-segment id (``{src}---{tgt}@@{type}``, `domain/artifact_id.py:159`), so it is
addressed the same way; the connection *list* keeps ``entity_id`` in the query because
removing it returns the whole collection.
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import STREAM, TYPED, RouteRow

ENTITY_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/entities", "collection", "entities_list_entities", TYPED,
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "POST", "/api/entities", "collection", "entities_create_entity", TYPED,
        mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}", "detail", "entities_read_entity", TYPED,
        identity_parameters=("artifact_id",), cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "PATCH", "/api/entities/{artifact_id}", "detail", "entities_update_entity", TYPED,
        identity_parameters=("artifact_id",), mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/entities/{artifact_id}", "detail", "entities_delete_entity", TYPED,
        identity_parameters=("artifact_id",), mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/context", "subresource", "entities_read_entity_context",
        TYPED,
        identity_parameters=("artifact_id",), cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/neighbors", "subresource", "connections_read_entity_neighbors",
        TYPED,
        identity_parameters=("artifact_id",), cache_directive="no-cache", conditional_read="etag",
        timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/entities/{artifact_id}/display-item", "subresource", "diagrams_read_entity_display_item",
        TYPED,
        identity_parameters=("artifact_id",), cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/entity-schemata/{artifact_type}", "detail", "entities_read_entity_schema",
        TYPED,
        identity_parameters=("artifact_type",), cache_directive="no-cache",
    ),
)

CONNECTION_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/connections", "collection", "connections_list_connections", TYPED,
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        # The induced subgraph over a set of entities, as distinct from one entity's star above.
        # Its own address rather than a second filter on the collection: the two are different
        # questions, and choosing between them by which parameter arrived is how one address came
        # to answer two — see `/api/ontology/classification` and `/api/ontology/pairs`.
        "GET", "/api/connections/among", "collection", "connections_list_connections_among", TYPED,
        cache_directive="no-cache", conditional_read="etag", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/connections", "collection", "connections_create_connection", TYPED,
        mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/connections/{connection_id}", "detail", "connections_update_connection",
        TYPED,
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/connections/{connection_id}", "detail", "connections_delete_connection",
        TYPED,
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/connections/{connection_id}/associated-entities", "subresource",
        "connections_update_connection_associations", TYPED,
        identity_parameters=("connection_id",), mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/connections/cleanup-broken-refs", "operation", "connections_cleanup_broken_references",
        TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
)

SEARCH_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/search", "collection", "entities_search_artifacts", TYPED,
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "GET", "/api/artifact-search", "collection", "entities_search_display_artifacts",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/entity-display-search", "collection", "diagrams_search_entity_display_items",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/reference-search", "collection", "documents_search_reference_artifacts",
        TYPED, cache_directive="no-cache", conditional_read="etag",
    ),
)

TAXONOMY_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/stats", "catalog", "taxonomy_read_repository_stats", TYPED,
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "GET", "/api/backend-identity", "catalog", "taxonomy_read_backend_identity",
        TYPED, cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/entity-taxonomy", "catalog", "taxonomy_read_entity_taxonomy",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/authoring-guidance", "catalog", "taxonomy_read_authoring_guidance",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/write-help", "catalog", "taxonomy_read_write_help", TYPED,
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/modules", "catalog", "taxonomy_list_modules", TYPED,
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/ontology/classification", "catalog", "connections_read_ontology_classification",
        TYPED, cache_directive="private",
    ),
    RouteRow(
        # Its own address because `/api/ontology/classification` is taken and means what one type
        # may connect to. Two questions, two addresses.
        "GET", "/api/ontology/classification-levels", "catalog",
        "taxonomy_read_classification_levels", TYPED, cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/ontology/element-appearance", "catalog", "taxonomy_read_element_appearance",
        TYPED, cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/ontology/pairs", "catalog", "connections_read_ontology_pair", TYPED,
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/relation-notations", "catalog", "connections_read_relation_notations",
        TYPED, cache_directive="private",
    ),
    RouteRow(
        "POST", "/api/identifiers/allocate", "operation", "entities_allocate_identifiers",
        TYPED,
    ),
    RouteRow("GET", "/api/events", "stream", "events_stream_events", STREAM, timeout_class="streaming"),
)
