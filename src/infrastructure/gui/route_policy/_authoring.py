"""Canonical route policy for the document, group and viewpoint authoring surfaces.

A group is identified by the pair (axis, slug) — both are required to name one, so both are
path parameters. Renaming re-files every member, which is a move rather than a field update,
so it keeps an explicit action segment instead of hiding inside ``PATCH``.

A viewpoint is identified by its slug. Its edit contract carries the whole definition, so the
canonical method is ``PUT``; the document edit contract is field-wise optional, so that one is
``PATCH``.
"""

from __future__ import annotations

from src.infrastructure.gui.route_policy._types import BODYLESS, MEDIA, RouteRow

_ARTIFACT = ("artifact_id",)
_GROUP = ("kind", "slug")
_SLUG = ("slug",)

DOCUMENT_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/documents", "collection", "documents_list_documents", "DocumentListResponse",
        cache_directive="no-cache", conditional_read="etag",
    ),
    RouteRow(
        "POST", "/api/documents", "collection", "documents_create_document", "WriteResultResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/documents/{artifact_id}", "detail", "documents_read_document",
        "DocumentDetailResponse", identity_parameters=_ARTIFACT, cache_directive="no-cache",
    ),
    RouteRow(
        "PATCH", "/api/documents/{artifact_id}", "detail", "documents_update_document",
        "WriteResultResponse", identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        # 204: a committed deletion has nothing to say. The dry-run outcome answers 200 with its
        # plan, declared on the route as an alternative rather than folded into this contract.
        "DELETE", "/api/documents/{artifact_id}", "detail", "documents_delete_document",
        BODYLESS, identity_parameters=_ARTIFACT, mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/document-types", "catalog", "documents_list_document_types",
        "DocumentTypeListResponse", cache_directive="private",
    ),
    RouteRow(
        "GET", "/api/document-schemata", "catalog", "documents_read_document_schemata",
        "DocumentSchemataResponse", cache_directive="no-cache",
    ),
)

GROUP_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/groups", "collection", "groups_list_groups", "GroupAxisListResponse",
        cache_directive="no-cache",
    ),
    RouteRow(
        "POST", "/api/groups", "collection", "groups_create_group", "GroupOperationResponse",
        mutation_domain="repository",
    ),
    RouteRow(
        "PATCH", "/api/groups/{kind}/{slug}", "detail", "groups_update_group", "GroupOperationResponse",
        identity_parameters=_GROUP, mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/groups/{kind}/{slug}", "detail", "groups_delete_group", "GroupOperationResponse",
        identity_parameters=_GROUP, mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/groups/{kind}/{slug}/rename", "operation", "groups_rename_group",
        "GroupOperationResponse", identity_parameters=_GROUP, mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/groups/{kind}/{slug}/archive", "operation", "groups_archive_group",
        "GroupOperationResponse", identity_parameters=_GROUP, mutation_domain="repository",
    ),
    RouteRow(
        "POST", "/api/groups/{kind}/{slug}/unarchive", "operation", "groups_unarchive_group",
        "GroupOperationResponse", identity_parameters=_GROUP, mutation_domain="repository",
    ),
)

VIEWPOINT_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/viewpoints", "collection", "viewpoints_list_viewpoints",
        "ViewpointDefinitionListResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "POST", "/api/viewpoints", "collection", "viewpoints_create_viewpoint",
        "ViewpointPersistResponse", mutation_domain="repository",
    ),
    RouteRow(
        "PUT", "/api/viewpoints/{slug}", "detail", "viewpoints_replace_viewpoint",
        "ViewpointPersistResponse", identity_parameters=_SLUG, mutation_domain="repository",
    ),
    RouteRow(
        # 204 like every other committed deletion. Its dry run answers 200 with the persist
        # envelope, and a deletion refused because diagrams still pin the slug answers 409
        # ``viewpoint_referenced`` — a refusal is an error, not a success carrying ``ok: false``.
        "DELETE", "/api/viewpoints/{slug}", "detail", "viewpoints_delete_viewpoint",
        BODYLESS, identity_parameters=_SLUG, mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/viewpoints/{slug}/referencers", "subresource",
        "viewpoints_list_viewpoint_referencers", "ViewpointReferencerListResponse",
        identity_parameters=_SLUG, cache_directive="no-cache",
    ),
    RouteRow(
        "GET", "/api/viewpoints/pins", "singleton", "viewpoints_read_viewpoint_pins",
        "ViewpointPinsResponse", cache_directive="no-cache",
    ),
    RouteRow(
        "PUT", "/api/viewpoints/pins", "singleton", "viewpoints_replace_viewpoint_pins",
        "ViewpointPinsResponse", mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/viewpoints/criteria-catalog", "catalog", "viewpoints_read_criteria_catalog",
        "ViewpointCriteriaCatalogResponse", cache_directive="private",
    ),
    RouteRow(
        "POST", "/api/viewpoints/execute", "operation", "viewpoints_execute_viewpoint",
        "ViewpointExecutionResponse", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/viewpoints/execute-diagram", "operation", "viewpoints_execute_viewpoint_diagram",
        "ViewpointDiagramExecutionResponse", timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/viewpoints/execute-projection", "operation",
        "viewpoints_execute_viewpoint_projection", "ViewpointProjectionResponse",
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/viewpoints/export-csv", "operation", "viewpoints_export_viewpoint_csv", MEDIA,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/viewpoints/export-render", "operation", "viewpoints_export_viewpoint_render", MEDIA,
        timeout_class="derived-graph",
    ),
    RouteRow(
        "POST", "/api/viewpoints/summarize", "operation", "viewpoints_summarize_viewpoint",
        "ViewpointSummaryResponse", timeout_class="derived-graph",
    ),
)
