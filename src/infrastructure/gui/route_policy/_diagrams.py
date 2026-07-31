"""Canonical route policy for the diagram, matrix and diagram-type surfaces.

A matrix is a diagram of the matrix kind, but it is created and replaced through its own
request contract, so ``/api/matrices`` is the collection those operations address; reads that
do not care about the kind stay on ``/api/diagrams``.

Diagram writes and renders are ``derived-graph``: they run PlantUML or a model traversal, and
the generic client timeout is not a promise this surface can keep.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._types import MEDIA, TYPED, RouteRow

_ID = ("artifact_id",)

DIAGRAM_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/diagrams", "collection", "diagrams_list_diagrams", TYPED,
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "POST", "/api/diagrams", "collection", "diagrams_create_diagram", TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}", "detail", "diagrams_read_diagram", TYPED,
        identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "PUT", "/api/diagrams/{artifact_id}", "detail", "diagrams_replace_diagram", TYPED,
        identity_parameters=_ID, mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "DELETE", "/api/diagrams/{artifact_id}", "detail", "diagrams_delete_diagram", TYPED,
        identity_parameters=_ID, mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/entities", "subresource", "diagrams_list_diagram_entities",
        TYPED,
        identity_parameters=_ID, cache_directive="no-cache", conditional_read="etag",
    ),
    # A construct the diagram owns, at the diagram's own address. Two segments for the two parts of
    # its composite identifier (`{diagram}#{entity_type}/{local_id}`), because a slash inside a single
    # path parameter ends the segment — and an encoded one is decoded back before routing, so the flat
    # entity address cannot carry these at all. Sub-entities of the diagram, addressed as such.
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/entities/{entity_type}/{local_id}", "detail",
        "diagrams_read_diagram_entity", TYPED,
        identity_parameters=("artifact_id", "entity_type", "local_id"),
        # No ETag: the conditional-read registry is a reviewed set of model-derived templates, and
        # claiming eligibility without being in it would be a promise the middleware does not keep.
        # Worth adding deliberately later; not worth claiming now.
        cache_directive="no-cache", conditional_read="none",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/connections", "subresource", "diagrams_list_diagram_connections",
        TYPED, identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/context", "subresource", "diagrams_read_diagram_context",
        TYPED, identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/svg", "subresource", "diagrams_read_diagram_svg", MEDIA,
        identity_parameters=_ID, cache_directive="no-cache", timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/download", "subresource", "diagrams_download_diagram_source",
        MEDIA, identity_parameters=_ID, timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/diagrams/{artifact_id}/viewpoint-projection", "subresource",
        "viewpoints_read_diagram_viewpoint_projection", TYPED,
        identity_parameters=_ID, cache_directive="no-cache", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/diagrams/{artifact_id}/sync", "operation", "diagrams_sync_diagram_to_model",
        TYPED,
        identity_parameters=_ID, mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "PATCH", "/api/diagrams/{artifact_id}/entities/{classifier_id}/metadata", "subresource",
        "diagrams_update_diagram_classifier_metadata", TYPED,
        identity_parameters=("artifact_id", "classifier_id"), mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/diagrams/{artifact_id}/entities/{classifier_id}/attributes/{attribute_id}/metadata",
        "subresource", "diagrams_update_diagram_attribute_metadata", TYPED,
        identity_parameters=("artifact_id", "classifier_id", "attribute_id"),
        mutation_domain="repository",
    ),
    RouteRow(
        "PUT", "/api/diagrams/{artifact_id}/edges/{edge_key}/label", "subresource",
        "diagrams_set_diagram_edge_label", TYPED,
        identity_parameters=("artifact_id", "edge_key"), mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/diagrams/preview", "operation", "diagrams_preview_diagram", TYPED,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/diagram-entity-discovery", "collection", "diagrams_discover_diagram_entities",
        TYPED, cache_directive="no-cache", timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/diagram-refs", "collection", "diagrams_list_diagram_references",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/diagram-images/{filename}", "detail", "diagrams_read_diagram_image", MEDIA,
        identity_parameters=("filename",), cache_directive="no-cache", timeout_class="derived-graph",
    ),
)

MATRIX_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "POST", "/api/matrices", "collection", "matrices_create_matrix", TYPED,
        mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "PUT", "/api/matrices/{artifact_id}", "detail", "matrices_replace_matrix", TYPED,
        identity_parameters=_ID, mutation_domain="repository", timeout_class="derived-graph",
    ),
    RouteRow(
        "GET", "/api/matrices/{artifact_id}/config", "subresource", "matrices_read_matrix_config",
        TYPED, identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "POST", "/api/matrices/preview", "operation", "matrices_preview_matrix", TYPED,
        timeout_class="derived-graph",
    ),
)

DIAGRAM_TYPE_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/diagram-types", "catalog", "diagrams_list_diagram_types", TYPED,
        cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/diagram-types/{diagram_type}/ui-config", "subresource",
        "diagrams_read_diagram_type_ui_config", TYPED,
        identity_parameters=("diagram_type",), cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/diagram-types/{diagram_type}/entity-types", "subresource",
        "diagrams_list_diagram_type_entity_types", TYPED,
        identity_parameters=("diagram_type",), cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/diagram-types/{diagram_type}/connection-types", "subresource",
        "diagrams_list_diagram_type_connection_types", TYPED,
        identity_parameters=("diagram_type",), cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/diagram-types/datatype/types", "collection", "diagrams_list_datatype_types",
        TYPED, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/diagram-types/datatype/types/{type_id}/usages", "subresource",
        "diagrams_list_datatype_type_usages", TYPED,
        identity_parameters=("type_id",), cache_directive="no-cache",
    ),
)
